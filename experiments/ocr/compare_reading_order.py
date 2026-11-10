
from __future__ import annotations

import argparse
import asyncio
import gc
import hashlib
import inspect
import json
import logging
import sys
import time

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from yomitoku import DocumentAnalyzer

from app.infrastructure.storage import LocalStorageAdapter


logger = logging.getLogger("compare_reading_order")


# ============================================================
# Argument
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare YomiToku reading_order modes "
            "using the same image."
        )
    )

    parser.add_argument(
        "image",
        nargs="?",
        help="Image file path.",
    )

    parser.add_argument(
        "--file-hash",
        help="Load image from DataCore CAS using file_hash.",
    )

    parser.add_argument(
        "--output-dir",
        default="experiments/ocr/reading_order_results",
        help="Output directory.",
    )

    parser.add_argument(
        "--device",
        default="cpu",
        choices=["cpu", "cuda", "mps"],
        help="YomiToku execution device.",
    )

    parser.add_argument(
        "--modes",
        nargs="+",
        default=["auto", "left2right"],
        choices=["auto", "left2right"],
        help="Reading order modes to compare.",
    )

    return parser.parse_args()


# ============================================================
# CAS
# ============================================================

async def load_from_cas(file_hash: str) -> bytes:
    storage = LocalStorageAdapter()

    data = await storage.load(file_hash)

    if data is None:
        raise FileNotFoundError(
            f"File not found in CAS: {file_hash}"
        )

    actual_hash = hashlib.sha256(data).hexdigest()

    if actual_hash != file_hash:
        raise ValueError(
            "CAS file hash mismatch.\n"
            f"Expected: {file_hash}\n"
            f"Actual:   {actual_hash}"
        )

    return data


def load_image(
    args: argparse.Namespace,
) -> tuple[np.ndarray, str]:

    if args.file_hash:
        image_bytes = asyncio.run(
            load_from_cas(args.file_hash)
        )

        image_id = args.file_hash

    elif args.image:
        image_path = Path(args.image)

        if not image_path.exists():
            raise FileNotFoundError(
                f"Image file not found: {image_path}"
            )

        image_bytes = image_path.read_bytes()

        image_id = hashlib.sha256(
            image_bytes
        ).hexdigest()

    else:
        raise ValueError(
            "Specify either an image path or --file-hash."
        )

    image = cv2.imdecode(
        np.frombuffer(
            image_bytes,
            dtype=np.uint8,
        ),
        cv2.IMREAD_COLOR,
    )

    if image is None:
        raise ValueError(
            "Failed to decode image."
        )

    return image, image_id


# ============================================================
# Serialization
# ============================================================

def to_json_dict(result: Any) -> dict[str, Any]:
    """
    Convert YomiToku result into a JSON-compatible dictionary.
    """

    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")

    if hasattr(result, "dict"):
        return result.dict()

    if hasattr(result, "to_json"):
        raw = result.to_json()

        if isinstance(raw, str):
            return json.loads(raw)

        if isinstance(raw, dict):
            return raw

    if isinstance(result, dict):
        return result

    raise TypeError(
        f"Unsupported result type: {type(result)}"
    )


# ============================================================
# Markdown
# ============================================================

def export_markdown(
    result: Any,
    out_path: Path,
) -> str:
    """
    Export YomiToku Markdown.

    YomiToku 0.15.0対応。

    to_markdown(out_path, export_figure=False)

    Figure出力を無効化して、Markdown本文を保存する。
    """

    if not hasattr(result, "to_markdown"):
        logger.warning(
            "Result does not provide to_markdown()."
        )
        return ""

    method = result.to_markdown

    signature = inspect.signature(method)
    parameters = signature.parameters

    # **kwargs を受け取れるか確認
    accepts_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )

    kwargs: dict[str, Any] = {}

    # export_figureを明示的に無効化
    if (
        "export_figure" in parameters
        or accepts_kwargs
    ):
        kwargs["export_figure"] = False

    # YomiToku 0.15.0:
    # to_markdown(out_path, **kwargs)
    if "out_path" in parameters:
        returned = method(
            str(out_path),
            **kwargs,
        )

    elif "output_path" in parameters:
        returned = method(
            str(out_path),
            **kwargs,
        )

    else:
        returned = method(**kwargs)

    # ファイル出力API
    if out_path.exists():
        return out_path.read_text(
            encoding="utf-8"
        )

    # 文字列返却API
    if isinstance(returned, str):
        return returned

    return ""


# ============================================================
# Visualization
# ============================================================

def save_visualization(
    image: Any,
    path: Path,
) -> None:

    if image is None:
        logger.warning(
            "Visualization is None: %s",
            path,
        )
        return

    if not cv2.imwrite(
        str(path),
        image,
    ):
        raise RuntimeError(
            f"Failed to save visualization: {path}"
        )


# ============================================================
# Result inspection
# ============================================================

def print_result_summary(
    result_dict: dict[str, Any],
) -> None:

    print("\nResult summary:")

    for key in (
        "words",
        "paragraphs",
        "tables",
        "figures",
    ):
        value = result_dict.get(key)

        if isinstance(value, list):
            print(
                f"  {key}: {len(value)}"
            )
        else:
            print(
                f"  {key}: {type(value).__name__}"
            )


# ============================================================
# Run one reading_order mode
# ============================================================

def run_one_mode(
    image: np.ndarray,
    mode: str,
    outdir: Path,
    device: str,
) -> None:

    outdir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("\n" + "=" * 70)
    print(f"Reading order: {mode}")
    print("=" * 70)

    started = time.perf_counter()

    # --------------------------------------------------------
    # Initialize analyzer
    # --------------------------------------------------------

    analyzer = DocumentAnalyzer(
        device=device,
        visualize=True,
        reading_order=mode,
    )

    # --------------------------------------------------------
    # OCR
    # --------------------------------------------------------

    result, ocr_vis, layout_vis = analyzer(image)

    elapsed = time.perf_counter() - started

    # --------------------------------------------------------
    # Native JSON
    # --------------------------------------------------------

    result_dict = to_json_dict(result)

    json_path = outdir / "native_result.json"

    json_path.write_text(
        json.dumps(
            result_dict,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Native Markdown
    # --------------------------------------------------------

    markdown_path = outdir / "native_markdown.md"

    markdown = export_markdown(
        result,
        markdown_path,
    )

    # APIがファイルを書き出さず、文字列を返した場合
    if not markdown_path.exists():
        markdown_path.write_text(
            markdown,
            encoding="utf-8",
        )

    # --------------------------------------------------------
    # Visualizations
    # --------------------------------------------------------

    save_visualization(
        ocr_vis,
        outdir / "ocr_visualization.png",
    )

    save_visualization(
        layout_vis,
        outdir / "layout_visualization.png",
    )

    # --------------------------------------------------------
    # Run information
    # --------------------------------------------------------

    height, width = image.shape[:2]

    run_info = {
        "reading_order": mode,
        "device": device,
        "elapsed_seconds": round(
            elapsed,
            3,
        ),
        "image_width": width,
        "image_height": height,
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    info_path = outdir / "run_info.json"

    info_path.write_text(
        json.dumps(
            run_info,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print(f"\nElapsed: {elapsed:.2f} sec")
    print(f"Output:  {outdir}")

    print_result_summary(
        result_dict
    )

    print("\nSaved files:")

    for path in sorted(outdir.iterdir()):
        print(
            f"  {path.name}"
        )

    # --------------------------------------------------------
    # Release memory
    # --------------------------------------------------------

    del analyzer
    del result
    del result_dict
    del ocr_vis
    del layout_vis

    gc.collect()


# ============================================================
# Main
# ============================================================

def main() -> int:

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s "
            "[%(levelname)s] "
            "%(message)s"
        ),
    )

    args = parse_args()

    try:

        # ----------------------------------------------------
        # Load image
        # ----------------------------------------------------

        image, image_id = load_image(args)

        height, width = image.shape[:2]

        print(f"Image ID: {image_id}")
        print(f"Image size: {width}x{height}")
        print(f"Device: {args.device}")
        print(f"Modes: {args.modes}")

        # ----------------------------------------------------
        # Output directory
        # ----------------------------------------------------

        root_dir = (
            Path(args.output_dir)
            / image_id
        )

        root_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # ----------------------------------------------------
        # Compare modes
        # ----------------------------------------------------

        for mode in args.modes:

            run_one_mode(
                image=image,
                mode=mode,
                outdir=root_dir / mode,
                device=args.device,
            )

        print("\n" + "=" * 70)
        print("Comparison completed.")
        print("=" * 70)

        print(f"Results: {root_dir}")

        return 0

    except Exception:

        logger.exception(
            "Comparison failed."
        )

        return 1


if __name__ == "__main__":
    sys.exit(main())

