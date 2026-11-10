from __future__ import annotations

import argparse
import asyncio
import mimetypes
import platform
import sys
import time
from pathlib import Path
from typing import Any

from experiments.common.io import base_manifest, new_experiment_dir, write_json


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the current DataCore OCR plugin without writing an L2 artifact."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file-hash", help="SHA-256 of an existing L1 CAS file")
    source.add_argument("--image", type=Path, help="Local image file")
    parser.add_argument("--output-dir", type=Path, default=Path("experiments/results"))
    parser.add_argument("--engine", choices=["yomitoku"], default="yomitoku")
    parser.add_argument("--label", default=None, help="Optional human-readable experiment label")
    return parser.parse_args()


async def load_cas_file(file_hash: str) -> tuple[bytes, str]:
    from sqlalchemy import select

    from app.infrastructure.db.session import AsyncSessionLocal
    from app.infrastructure.storage import LocalStorageAdapter
    from app.layers.l1_raw.models import L1File

    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(L1File).where(L1File.file_hash == file_hash)
            )
        ).scalar_one_or_none()

        if row is None:
            raise ValueError(f"L1 file not found: {file_hash}")
        mime_type = row.mime_type

    content = await LocalStorageAdapter().load(file_hash)
    if content is None:
        raise FileNotFoundError(f"CAS object not found: {file_hash}")
    return content, mime_type


async def main():
    args = parse_args()
    started = time.perf_counter()
    out_dir = new_experiment_dir(args.output_dir)
    manifest: dict[str, Any] = base_manifest("ocr")
    manifest.update({
        "label": args.label,
        "engine": args.engine,
        "source": {},
        "runtime": {"python": sys.version, "platform": platform.platform()},
    })

    try:
        if args.file_hash:
            image_bytes, mime_type = await load_cas_file(args.file_hash)
            manifest["source"] = {"type": "cas", "file_hash": args.file_hash}
        else:
            image_path = args.image.expanduser().resolve()
            if not image_path.is_file():
                raise FileNotFoundError(image_path)
            image_bytes = image_path.read_bytes()
            mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
            manifest["source"] = {
                "type": "local_file",
                "file_name": image_path.name,
                "file_size": len(image_bytes),
            }

        manifest["source"]["mime_type"] = mime_type
        manifest["source"]["byte_length"] = len(image_bytes)

        if args.engine == "yomitoku":
            from app.layers.l2_extracted.ocr.yomitoku_v1 import YomitokuV1Plugin
            plugin = YomitokuV1Plugin()
        else:
            raise ValueError(f"Unsupported engine: {args.engine}")

        if not any(mime_type.startswith(mt) for mt in plugin.supported_mimetypes):
            raise ValueError(
                f"{args.engine} does not support MIME type {mime_type}; "
                f"supported={plugin.supported_mimetypes}"
            )

        manifest["plugin"] = {
            "tool_name": plugin.tool_name,
            "tool_version": plugin.tool_version,
            "config": "plugin defaults; no DB registration",
        }

        result = await asyncio.to_thread(
            plugin.process_from_memory, image_bytes, mime_type
        )
        elapsed = time.perf_counter() - started

        payload = {
            "full_text": result.get("full_text", ""),
            "words": result.get("words", []),
            "metadata_json": result.get("metadata_json", {}),
        }
        write_json(out_dir / "ocr_output.json", payload)

        manifest.update({
            "status": "success",
            "elapsed_seconds": round(elapsed, 3),
            "output": {
                "text_characters": len(payload["full_text"]),
                "word_count": len(payload["words"]),
                "metadata_keys": list(payload["metadata_json"].keys()),
            },
        })
        write_json(out_dir / "manifest.json", manifest)
        print(f"OCR experiment saved: {out_dir}")
        print(f"Elapsed: {elapsed:.2f}s | chars: {len(payload['full_text'])} | words: {len(payload['words'])}")

    except Exception as exc:
        manifest.update({
            "status": "failed",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "error": {"type": type(exc).__name__, "message": str(exc)},
        })
        write_json(out_dir / "manifest.json", manifest)
        write_json(out_dir / "error.json", manifest["error"])
        raise


if __name__ == "__main__":
    asyncio.run(main())
