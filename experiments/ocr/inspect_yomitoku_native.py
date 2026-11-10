
#!/usr/bin/env python3
"""
YomiToku Native OCR Experiment

- --file-hash: DataCore L1 CASから原本を取得
- image: 画像ファイルを直接指定
- YomiToku DocumentAnalyzerの標準設定で解析
- 独自の拡大・回転・読み順補正は行わない
- ネイティブ結果と可視化画像を保存
"""

import argparse
import asyncio
import hashlib
import inspect
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yomitoku

from app.infrastructure.storage import LocalStorageAdapter


# --------------------------------------------------
# JSON変換
# --------------------------------------------------

def jsonable(obj: Any) -> Any:

    if obj is None:
        return None

    if isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, np.ndarray):
        return obj.tolist()

    if isinstance(obj, np.generic):
        return obj.item()

    if isinstance(obj, dict):
        return {
            str(k): jsonable(v)
            for k, v in obj.items()
        }

    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]

    if hasattr(obj, "model_dump"):
        try:
            return jsonable(obj.model_dump(mode="json"))
        except Exception:
            pass

    if hasattr(obj, "dict") and callable(obj.dict):
        try:
            return jsonable(obj.dict())
        except Exception:
            pass

    if hasattr(obj, "__dict__"):
        try:
            return jsonable(vars(obj))
        except Exception:
            pass

    return str(obj)


def save_json(path: Path, data: Any) -> None:

    path.write_text(
        json.dumps(
            jsonable(data),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# --------------------------------------------------
# L1 CAS
# --------------------------------------------------

async def load_from_cas(file_hash: str) -> bytes:

    if len(file_hash) != 64:
        raise ValueError("file_hash must be a SHA-256 hex string")

    try:
        int(file_hash, 16)
    except ValueError as exc:
        raise ValueError("file_hash must contain hexadecimal characters") from exc

    storage = LocalStorageAdapter()

    content = await storage.load(file_hash)

    if content is None:
        raise FileNotFoundError(
            f"L1 CAS file not found: {file_hash}"
        )

    # CASのキーと実ファイルの整合性を確認
    actual_hash = hashlib.sha256(content).hexdigest()

    if actual_hash != file_hash:
        raise ValueError(
            "CAS hash mismatch: "
            f"expected={file_hash}, actual={actual_hash}"
        )

    return content


# --------------------------------------------------
# Visualization
# --------------------------------------------------

def save_visualization(path: Path, image: Any) -> bool:

    if image is None:
        return False

    if not isinstance(image, np.ndarray):
        print(
            f"[WARN] Unsupported visualization type: "
            f"{type(image)}"
        )
        return False

    if image.size == 0:
        return False

    if not cv2.imwrite(str(path), image):
        print(f"[WARN] Failed to save: {path}")
        return False

    return True


# --------------------------------------------------
# Native result inspection
# --------------------------------------------------

def summarize_result(result: Any) -> dict:

    summary = {
        "result_type": (
            f"{type(result).__module__}."
            f"{type(result).__name__}"
        ),
        "attributes": [],
        "collections": {},
    }

    if hasattr(result, "__dict__"):
        summary["attributes"] = list(vars(result).keys())

    for name in (
        "paragraphs",
        "words",
        "tables",
        "figures",
    ):
        value = getattr(result, name, None)

        if value is not None:
            summary["collections"][name] = {
                "type": type(value).__name__,
                "count": (
                    len(value)
                    if hasattr(value, "__len__")
                    else None
                ),
            }

    return summary


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description="YomiToku native OCR experiment"
    )

    source = parser.add_mutually_exclusive_group(required=True)

    source.add_argument(
        "--file-hash",
        help="L1 CAS SHA-256 file_hash",
    )

    source.add_argument(
        "image",
        nargs="?",
        type=Path,
        help="画像ファイルを直接指定",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/ocr/native_results"),
    )

    parser.add_argument(
        "--device",
        choices=["cpu", "cuda", "mps"],
        default=None,
    )

    args = parser.parse_args()

    # --------------------------------------------------
    # 1. 原本取得
    # --------------------------------------------------

    if args.file_hash:

        print(f"[CAS] Loading: {args.file_hash}")

        image_bytes = asyncio.run(
            load_from_cas(args.file_hash)
        )

        source_id = args.file_hash

    else:

        image_path = args.image.resolve()

        if not image_path.is_file():
            raise FileNotFoundError(image_path)

        image_bytes = image_path.read_bytes()
        source_id = image_path.stem

    actual_hash = hashlib.sha256(image_bytes).hexdigest()

    print(f"[INPUT] bytes={len(image_bytes)}")
    print(f"[INPUT] sha256={actual_hash}")

    # --------------------------------------------------
    # 2. 画像デコード
    # --------------------------------------------------

    nparr = np.frombuffer(image_bytes, np.uint8)

    image = cv2.imdecode(
        nparr,
        cv2.IMREAD_COLOR,
    )

    if image is None:
        raise ValueError("Image decoding failed")

    height, width = image.shape[:2]

    print(f"[INPUT] size={width}x{height}")

    # --------------------------------------------------
    # 3. 出力先
    # --------------------------------------------------

    output_dir = (
        args.output_dir.resolve() / source_id
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    cv2.imwrite(
        str(output_dir / "input.png"),
        image,
    )

    # --------------------------------------------------
    # 4. YomiToku情報
    # --------------------------------------------------

    version = getattr(
        yomitoku,
        "__version__",
        "unknown",
    )

    analyzer_class = getattr(
        yomitoku,
        "DocumentAnalyzer",
        None,
    )

    if analyzer_class is None:
        raise RuntimeError(
            "yomitoku.DocumentAnalyzer not found"
        )

    signature = inspect.signature(analyzer_class)

    print(f"[YOMITOKU] version={version}")
    print(f"[YOMITOKU] signature={signature}")

    # --------------------------------------------------
    # 5. DocumentAnalyzer初期化
    # --------------------------------------------------

    init_kwargs = {}

    # 可視化がサポートされている場合のみ有効化
    if "visualize" in signature.parameters:
        init_kwargs["visualize"] = True

    if (
        args.device is not None
        and "device" in signature.parameters
    ):
        init_kwargs["device"] = args.device

    print(f"[INIT] kwargs={init_kwargs}")

    analyzer = analyzer_class(**init_kwargs)

    # --------------------------------------------------
    # 6. YomiToku推論
    # --------------------------------------------------

    print("[RUN] DocumentAnalyzer started")

    started_at = time.perf_counter()

    # 原本画像をそのまま渡す
    # リサイズ・回転・独自前処理なし
    inference_output = analyzer(image)

    elapsed = time.perf_counter() - started_at

    print(f"[RUN] elapsed={elapsed:.2f}s")

    # --------------------------------------------------
    # 7. 戻り値の分解
    # --------------------------------------------------

    ocr_vis = None
    layout_vis = None

    if isinstance(inference_output, (tuple, list)):

        if not inference_output:
            raise RuntimeError("Empty inference result")

        result = inference_output[0]

        if len(inference_output) > 1:
            ocr_vis = inference_output[1]

        if len(inference_output) > 2:
            layout_vis = inference_output[2]

    else:
        result = inference_output

    if result is None:
        raise RuntimeError("YomiToku returned None")

    # --------------------------------------------------
    # 8. ネイティブ結果保存
    # --------------------------------------------------

    save_json(
        output_dir / "native_result.json",
        result,
    )

    summary = summarize_result(result)

    # --------------------------------------------------
    # 9. ネイティブMarkdown
    # --------------------------------------------------

    markdown_path = output_dir / "native_markdown.md"

    markdown_error = None

    to_markdown = getattr(
        result,
        "to_markdown",
        None,
    )

    if callable(to_markdown):

        try:
            markdown = to_markdown(
                str(markdown_path),
                export_figure=False,
            )

            if isinstance(markdown, str):
                markdown_path.write_text(
                    markdown,
                    encoding="utf-8",
                )

        except Exception as exc:

            markdown_error = (
                f"{type(exc).__name__}: {exc}"
            )

            print(f"[WARN] Markdown: {markdown_error}")

    else:
        markdown_error = "to_markdown() not available"

    # --------------------------------------------------
    # 10. 可視化画像保存
    # --------------------------------------------------

    ocr_saved = save_visualization(
        output_dir / "ocr_visualization.png",
        ocr_vis,
    )

    layout_saved = save_visualization(
        output_dir / "layout_visualization.png",
        layout_vis,
    )

    # --------------------------------------------------
    # 11. 実験情報
    # --------------------------------------------------

    run_info = {

        "executed_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "source": {
            "file_hash": actual_hash,
            "source_id": source_id,
            "bytes": len(image_bytes),
            "width": width,
            "height": height,
        },

        "yomitoku": {
            "version": version,
            "class": str(analyzer_class),
            "signature": str(signature),
            "constructor_kwargs": init_kwargs,
            "reading_order": "default",
        },

        "execution": {
            "elapsed_seconds": elapsed,
            "resize": False,
            "rotation": False,
            "custom_sort": False,
            "custom_direction_detection": False,
        },

        "output": {
            "markdown_error": markdown_error,
            "ocr_visualization_saved": ocr_saved,
            "layout_visualization_saved": layout_saved,
        },

        "native_schema": summary,
    }

    save_json(
        output_dir / "run_info.json",
        run_info,
    )

    # --------------------------------------------------
    # 12. 結果表示
    # --------------------------------------------------

    print("\n========== NATIVE RESULT ==========")

    print(json.dumps(
        summary,
        ensure_ascii=False,
        indent=2,
    ))

    print("\n========== OUTPUT FILES ==========")

    for path in sorted(output_dir.iterdir()):
        print(path)

    print("\n[OK] YomiToku native experiment completed")


if __name__ == "__main__":
    main()

