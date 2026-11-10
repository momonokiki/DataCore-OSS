#!/usr/bin/env python3
"""
Inspect YomiToku's native reading order and Markdown output without writing to L2/L3.

Run from the DataCore repository root:
  python -m experiments.ocr.inspect_yomitoku_order --file-hash <SHA256>
or:
  python -m experiments.ocr.inspect_yomitoku_order --image /path/to/receipt.jpg

Outputs:
  experiments/results/<run_id>/
    native_markdown.md       YomiToku's own Markdown serialization
    plugin_full_text.md      DataCore plugin's final full_text
    plugin_words_sorted.json DataCore plugin's normalized/sorted words
    native_structure.json    introspection of native YomiToku result
    summary.json             result type, available structure fields, metadata
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.layers.l2_extracted.ocr.yomitoku_v1 import YomitokuV1Plugin


class CapturingReader:
    """Capture the exact native result while letting the DataCore plugin run normally."""

    def __init__(self, reader: Any):
        self.reader = reader
        self.results: list[Any] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        result = self.reader(*args, **kwargs)
        self.results.append(result)
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self.reader, name)


def jsonable(value: Any, depth: int = 0) -> Any:
    """Convert native result objects to bounded JSON-safe data."""
    if depth > 8:
        return f"<max-depth:{type(value).__name__}>"

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, np.ndarray):
        if value.size > 100_000:
            return {
                "__type__": "ndarray",
                "shape": list(value.shape),
                "dtype": str(value.dtype),
                "omitted": True,
            }
        return value.tolist()

    if isinstance(value, np.generic):
        return value.item()

    if isinstance(value, dict):
        return {
            str(k): jsonable(v, depth + 1)
            for k, v in list(value.items())[:500]
        }

    if isinstance(value, (list, tuple)):
        return [jsonable(v, depth + 1) for v in value[:2000]]

    # Pydantic v2 / v1
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return jsonable(model_dump(), depth + 1)
        except Exception:
            pass

    dict_method = getattr(value, "dict", None)
    if callable(dict_method):
        try:
            return jsonable(dict_method(), depth + 1)
        except Exception:
            pass

    attrs: dict[str, Any] = {}
    raw_dict = getattr(value, "__dict__", None)
    if isinstance(raw_dict, dict):
        for key, item in list(raw_dict.items())[:200]:
            if not key.startswith("_"):
                attrs[key] = jsonable(item, depth + 1)

    if attrs:
        return {
            "__type__": f"{type(value).__module__}.{type(value).__name__}",
            **attrs,
        }

    return {
        "__type__": f"{type(value).__module__}.{type(value).__name__}",
        "__repr__": repr(value)[:1000],
    }


def describe_native_result(result: Any) -> dict[str, Any]:
    """Expose public attributes that may contain paragraph/line/layout structure."""
    keys = (
        "markdown", "text", "full_text", "words", "paragraphs",
        "lines", "blocks", "pages", "layout", "tables", "figures",
    )
    found: dict[str, Any] = {
        "__type__": f"{type(result).__module__}.{type(result).__name__}",
    }

    if isinstance(result, dict):
        for key in keys:
            if key in result:
                found[key] = jsonable(result[key])
        found["all_keys"] = [str(k) for k in result.keys()]
        return found

    for key in keys:
        try:
            value = getattr(result, key)
        except Exception:
            continue
        if value is not None:
            found[key] = jsonable(value)

    # Record public names to make undocumented/version-specific fields visible.
    try:
        found["public_attributes"] = [
            name for name in dir(result)
            if not name.startswith("_")
        ][:300]
    except Exception:
        pass

    if not any(k in found for k in keys):
        found["object_repr"] = repr(result)[:2000]

    return found


async def load_cas_file(file_hash: str) -> tuple[bytes, str]:
    """Load the original image through DataCore's existing L1/CAS adapters."""
    from sqlalchemy import select
    from app.infrastructure.db.session import AsyncSessionLocal
    from app.infrastructure.storage import LocalStorageAdapter
    from app.layers.l1_raw.models import L1File

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(L1File).where(L1File.file_hash == file_hash)
        )
        l1_file = result.scalars().first()
        if l1_file is None:
            raise RuntimeError(f"L1 file not found: {file_hash}")

        mime_type = l1_file.mime_type
        storage = LocalStorageAdapter()
        content = await storage.load(file_hash)

    if content is None:
        raise FileNotFoundError(f"CAS file not found: {file_hash}")
    return content, mime_type


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect YomiToku native reading order / Markdown."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file-hash", help="SHA-256 of an existing DataCore L1 file")
    source.add_argument("--image", type=Path, help="Local image path")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: experiments/results/<timestamp>_<id>)",
    )
    return parser.parse_args()


async def get_image_bytes(args: argparse.Namespace) -> tuple[bytes, str]:
    if args.file_hash:
        return await load_cas_file(args.file_hash)

    path = args.image.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    suffix = path.suffix.lower()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix, "application/octet-stream")
    return path.read_bytes(), mime


def main() -> None:
    args = parse_args()
    file_bytes, mime_type = asyncio.run(get_image_bytes(args))

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    output_dir = args.output_dir or Path("experiments/results") / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    plugin = YomitokuV1Plugin()
    original_get_reader = plugin._get_reader
    capturing_reader = CapturingReader(original_get_reader())
    plugin._get_reader = lambda: capturing_reader  # capture without running OCR twice

    # Run the same preprocessing, inference, rotation handling, normalization,
    # sorting and Markdown conversion as DataCore's current YomiToku plugin.
    plugin_result = plugin.process_from_memory(file_bytes, mime_type)
    if not capturing_reader.results:
        raise RuntimeError(
            "YomiToku inference result was not captured. "
            "Check whether process_from_memory uses plugin._get_reader()."
        )

    # Keep every native inference result (e.g. each rotation candidate).
    # The plugin's final full_text is the authoritative selected result.
    candidate_summaries = []
    selected_candidate = None
    candidates_dir = output_dir / "native_candidates"
    candidates_dir.mkdir(exist_ok=True)

    for index, native_out in enumerate(capturing_reader.results):
        native_result = (
            native_out[0]
            if isinstance(native_out, (tuple, list)) and native_out
            else native_out
        )
        if native_result is None:
            continue

        candidate_markdown = plugin._to_markdown(native_result)
        candidate_structure = describe_native_result(native_result)
        candidate_words = (
            native_result.get("words", [])
            if isinstance(native_result, dict)
            else getattr(native_result, "words", [])
        ) or []

        stem = f"candidate_{index:02d}"
        (candidates_dir / f"{stem}.md").write_text(
            candidate_markdown, encoding="utf-8"
        )
        (candidates_dir / f"{stem}.json").write_text(
            json.dumps(candidate_structure, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        is_selected = candidate_markdown.strip() == plugin_result["full_text"].strip()
        if is_selected:
            selected_candidate = index

        candidate_summaries.append({
            "index": index,
            "type": f"{type(native_result).__module__}.{type(native_result).__name__}",
            "word_count": len(candidate_words),
            "markdown_chars": len(candidate_markdown),
            "matches_plugin_full_text": is_selected,
        })

    # The DataCore plugin's full_text is the selected native Markdown output.
    native_markdown = plugin_result["full_text"]
    (output_dir / "native_markdown.md").write_text(
        native_markdown, encoding="utf-8"
    )
    (output_dir / "native_structure.json").write_text(
        json.dumps(
            {
                "selected_candidate_index": selected_candidate,
                "candidates": candidate_summaries,
                "note": "See native_candidates/ for each captured native result.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "plugin_full_text.md").write_text(
        plugin_result["full_text"], encoding="utf-8"
    )
    (output_dir / "plugin_words_sorted.json").write_text(
        json.dumps(plugin_result["words"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "native_structure.json").write_text(
        json.dumps(
            describe_native_result(native_result),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    native_words_total = sum(item["word_count"] for item in candidate_summaries)

    summary = {
        "input": {
            "file_hash": args.file_hash,
            "image_path": str(args.image) if args.image else None,
            "mime_type": mime_type,
            "bytes": len(file_bytes),
        },
        "yomitoku": {
            "version": None,
            "native_result_type": (
                f"{type(native_result).__module__}.{type(native_result).__name__}"
            ),
            "native_candidate_count": len(candidate_summaries),
            "native_candidate_word_count_total": native_words_total,
            "selected_candidate_index": selected_candidate,
            "candidates": candidate_summaries,
            "native_markdown_chars": len(native_markdown),
            "plugin_full_text_chars": len(plugin_result["full_text"]),
            "plugin_sorted_word_count": len(plugin_result["words"]),
            "plugin_metadata": plugin_result.get("metadata_json", {}),
            "native_attributes": (
                list(native_result.keys())
                if isinstance(native_result, dict)
                else [
                    name for name in dir(native_result)
                    if not name.startswith("_")
                ][:300]
            ),
        },
        "outputs": [
            "native_markdown.md",
            "plugin_full_text.md",
            "plugin_words_sorted.json",
            "native_structure.json",
        ],
    }

    try:
        import yomitoku
        summary["yomitoku"]["version"] = getattr(yomitoku, "__version__", None)
    except Exception:
        pass

    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] Results: {output_dir}")
    print(f"  Native Markdown : {len(native_markdown)} chars")
    print(f"  Plugin full_text: {len(plugin_result['full_text'])} chars")
    print(f"  Native candidates: {len(candidate_summaries)}")
    print(f"  Selected candidate: {selected_candidate}")
    print(f"  Plugin words    : {len(plugin_result['words'])}")
    print("  Check native_structure.json for paragraphs/lines/blocks fields.")
    print("  No L2/L3 records were created.")


if __name__ == "__main__":
    main()
