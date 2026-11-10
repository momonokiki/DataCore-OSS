
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import time

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from yomitoku import DocumentAnalyzer


DEFAULT_STORAGE = Path("/app/storage")
DEFAULT_OUTPUT = Path("experiments/ocr/output")

SCALES = (1.0, 2.0)
DEFAULT_MODES = ("auto", "left2right")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def find_cas_file(file_hash: str, storage: Path) -> Path:
    """
    CASからfile_hashに対応するファイルを検索する。

    想定:
      storage/<prefix>/<filename>
      storage以下の任意の階層
    """
    if len(file_hash) != 64:
        raise ValueError("file_hash must be a 64-character SHA-256")

    candidates = []

    for path in storage.rglob("*"):
        if not path.is_file():
            continue

        if path.name == file_hash:
            candidates.append(path)
        elif path.stem == file_hash:
            candidates.append(path)

    if not candidates:
        raise FileNotFoundError(
            f"CAS file not found: {file_hash} (storage={storage})"
        )

    if len(candidates) > 1:
        raise RuntimeError(
            "Multiple CAS files found:\n"
            + "\n".join(str(p) for p in candidates)
        )

    return candidates[0]


def load_image(
    image_path: Path,
    expected_hash: str | None = None,
) -> tuple[np.ndarray, str]:
    if not image_path.exists():
        raise FileNotFoundError(image_path)

    actual_hash = sha256_file(image_path)

    if expected_hash and actual_hash != expected_hash:
        raise ValueError(
            "SHA-256 mismatch\n"
            f"expected: {expected_hash}\n"
            f"actual:   {actual_hash}"
        )

    image_bytes = np.fromfile(str(image_path), dtype=np.uint8)
    image = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)

    if image is None:
        raise ValueError(f"Failed to decode image: {image_path}")

    return image, actual_hash


def resize_image(
    image: np.ndarray,
    scale: float,
) -> np.ndarray:
    if scale == 1.0:
        return image.copy()

    height, width = image.shape[:2]

    new_width = round(width * scale)
    new_height = round(height * scale)

    return cv2.resize(
        image,
        (new_width, new_height),
        interpolation=cv2.INTER_CUBIC,
    )


def json_default(value: Any):
    if isinstance(value, np.ndarray):
        return value.tolist()

    if isinstance(value, np.generic):
        return value.item()

    if isinstance(value, Path):
        return str(value)

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")

    if hasattr(value, "dict"):
        return value.dict()

    if hasattr(value, "__dict__"):
        return vars(value)

    return str(value)


def to_serializable(value: Any):
    if value is None:
        return None

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")

    if hasattr(value, "dict"):
        return value.dict()

    if isinstance(value, (list, tuple)):
        return [to_serializable(v) for v in value]

    if isinstance(value, dict):
        return {
            str(k): to_serializable(v)
            for k, v in value.items()
        }

    return value


def save_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            default=json_default,
        ),
        encoding="utf-8",
    )


def save_visualization(
    image: np.ndarray | None,
    path: Path,
):
    if image is None:
        return

    path.parent.mkdir(parents=True, exist_ok=True)

    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"Failed to save visualization: {path}")


def export_markdown(result: Any, output_path: Path):
    """
    YomiTokuのto_markdown API差異に対応する。

    YomiToku 0.15.0:
      to_markdown(out_path, export_figure=False)

    **kwargsを受け取る実装にもexport_figure=Falseを渡す。
    """
    method = getattr(result, "to_markdown", None)

    if not callable(method):
        return {
            "status": "unsupported",
            "reason": "to_markdown method not found",
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    signature = inspect.signature(method)
    parameters = signature.parameters

    kwargs = {}

    if "out_path" in parameters:
        kwargs["out_path"] = str(output_path)
    elif "output_path" in parameters:
        kwargs["output_path"] = str(output_path)
    else:
        has_var_keyword = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in parameters.values()
        )

        if has_var_keyword:
            kwargs["out_path"] = str(output_path)
        else:
            return {
                "status": "unsupported",
                "reason": f"Unknown to_markdown signature: {signature}",
            }

    if (
        "export_figure" in parameters
        or any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in parameters.values()
        )
    ):
        kwargs["export_figure"] = False

    returned = method(**kwargs)

    # 実装によってはMarkdown文字列を返す場合がある
    if isinstance(returned, str):
        output_path.write_text(returned, encoding="utf-8")

    if output_path.exists():
        return {
            "status": "saved",
            "path": str(output_path),
        }

    return {
        "status": "called",
        "path": str(output_path),
        "return_type": type(returned).__name__,
    }


def run_ocr(
    image: np.ndarray,
    scale: float,
    mode: str,
    device: str,
    output_dir: Path,
):
    height, width = image.shape[:2]

    run_dir = output_dir / f"scale_{scale:.1f}" / mode
    run_dir.mkdir(parents=True, exist_ok=True)

    processed_image = resize_image(image, scale)

    processed_height, processed_width = processed_image.shape[:2]

    print()
    print("=" * 70)
    print(f"Scale       : {scale}")
    print(f"Reading     : {mode}")
    print(f"Original    : {width} x {height}")
    print(f"Processed   : {processed_width} x {processed_height}")
    print(f"Output      : {run_dir}")
    print("=" * 70)

    # 前処理後の画像も保存する
    save_visualization(
        processed_image,
        run_dir / "input.png",
    )

    started_at = time.perf_counter()

    analyzer = DocumentAnalyzer(
        device=device,
        visualize=True,
        reading_order=mode,
    )

    result = analyzer(processed_image)

    elapsed = time.perf_counter() - started_at

    # visualize=Trueの場合:
    # (results, ocr_vis, layout_vis)
    if isinstance(result, tuple):
        native_result = result[0]
        ocr_vis = result[1] if len(result) > 1 else None
        layout_vis = result[2] if len(result) > 2 else None
    else:
        native_result = result
        ocr_vis = None
        layout_vis = None

    # OCR結果JSON
    serialized = to_serializable(native_result)

    save_json(
        run_dir / "native_result.json",
        serialized,
    )

    # Markdown
    markdown_info = export_markdown(
        native_result,
        run_dir / "native_markdown.md",
    )

    # 可視化画像
    save_visualization(
        ocr_vis,
        run_dir / "ocr_visualization.png",
    )

    save_visualization(
        layout_vis,
        run_dir / "layout_visualization.png",
    )

    # words / paragraphs / tablesの数
    def get_count(name: str):
        value = getattr(native_result, name, None)

        if value is None and isinstance(serialized, dict):
            value = serialized.get(name)

        return len(value) if value is not None else None

    run_info = {
        "scale": scale,
        "reading_order": mode,
        "device": device,
        "original_width": width,
        "original_height": height,
        "processed_width": processed_width,
        "processed_height": processed_height,
        "elapsed_seconds": round(elapsed, 3),
        "words_count": get_count("words"),
        "paragraphs_count": get_count("paragraphs"),
        "tables_count": get_count("tables"),
        "markdown": markdown_info,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }

    save_json(
        run_dir / "run_info.json",
        run_info,
    )

    print(json.dumps(run_info, ensure_ascii=False, indent=2))

    return run_info


def main():
    parser = argparse.ArgumentParser(
        description="Compare YomiToku OCR results at original and 2x image scales."
    )

    parser.add_argument(
        "image",
        nargs="?",
        help="Image file path",
    )

    parser.add_argument(
        "--file-hash",
        help="SHA-256 hash of a CAS image",
    )

    parser.add_argument(
        "--storage",
        default=str(DEFAULT_STORAGE),
        help=f"CAS storage directory (default: {DEFAULT_STORAGE})",
    )

    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT),
        help=f"Output directory (default: {DEFAULT_OUTPUT})",
    )

    parser.add_argument(
        "--device",
        default="cpu",
        help="YomiToku device (default: cpu)",
    )

    parser.add_argument(
        "--modes",
        nargs="+",
        default=list(DEFAULT_MODES),
        choices=["auto", "left2right"],
        help="Reading order modes",
    )

    args = parser.parse_args()

    if not args.image and not args.file_hash:
        parser.error("Specify image path or --file-hash")

    if args.image and args.file_hash:
        parser.error("Specify either image path or --file-hash, not both")

    storage = Path(args.storage)

    if args.file_hash:
        image_path = find_cas_file(
            args.file_hash,
            storage,
        )
        expected_hash = args.file_hash
    else:
        image_path = Path(args.image)
        expected_hash = None

    image, file_hash = load_image(
        image_path,
        expected_hash,
    )

    output_dir = Path(args.output_dir) / file_hash
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Image     : {image_path}")
    print(f"SHA-256   : {file_hash}")
    print(f"Size      : {image.shape[1]} x {image.shape[0]}")
    print(f"Scales    : {SCALES}")
    print(f"Modes     : {args.modes}")

    all_results = []

    # 同じ原画像から原寸・2倍を生成して比較する
    for scale in SCALES:
        for mode in args.modes:
            info = run_ocr(
                image=image,
                scale=scale,
                mode=mode,
                device=args.device,
                output_dir=output_dir,
            )

            all_results.append(info)

    # 全条件の比較サマリー
    save_json(
        output_dir / "comparison_summary.json",
        {
            "file_hash": file_hash,
            "image_path": str(image_path),
            "original_width": image.shape[1],
            "original_height": image.shape[0],
            "scales": list(SCALES),
            "modes": args.modes,
            "results": all_results,
        },
    )

    print()
    print("=" * 70)
    print("Comparison completed")
    print(f"Output: {output_dir.resolve()}")
    print("=" * 70)


if __name__ == "__main__":
    main()

