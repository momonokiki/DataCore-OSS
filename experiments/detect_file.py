import argparse
import asyncio
import json
import logging
import sys

from sqlalchemy import select

from app.infrastructure.db.session import AsyncSessionLocal
from app.infrastructure.storage import LocalStorageAdapter
from app.layers.l1_raw.models import L1File, L1FileUpload
from app.layers.l2_extracted.media_info.detector import MediaTypeDetector


logger = logging.getLogger(__name__)


async def list_files(limit: int = 50):
    """L1に登録されているアップロードファイルを一覧表示する。"""

    async with AsyncSessionLocal() as session:
        stmt = (
            select(
                L1FileUpload.original_filename,
                L1FileUpload.created_at,
                L1File.file_hash,
                L1File.mime_type,
                L1File.file_size_bytes,
            )
            .join(
                L1File,
                L1File.file_hash == L1FileUpload.file_hash,
            )
            .order_by(L1FileUpload.created_at.desc())
            .limit(limit)
        )

        result = await session.execute(stmt)
        rows = result.all()

    if not rows:
        print("アップロード済みファイルがありません。")
        return

    print(f"\nL1 Upload Files (最新 {len(rows)} 件)")
    print("=" * 100)

    for index, row in enumerate(rows, start=1):
        print(f"[{index}] {row.original_filename}")
        print(f"    file_hash : {row.file_hash}")
        print(f"    MIME      : {row.mime_type}")
        print(f"    Size      : {row.file_size_bytes:,} bytes")
        print(f"    Uploaded  : {row.created_at}")
        print("-" * 100)


async def detect_file(file_hash: str) -> dict:
    """L1 CASからファイルを取得してDetectorを実行する。"""

    async with AsyncSessionLocal() as session:
        stmt = (
            select(
                L1File,
                L1FileUpload.original_filename,
            )
            .join(
                L1FileUpload,
                L1FileUpload.file_hash == L1File.file_hash,
            )
            .where(L1File.file_hash == file_hash)
            .order_by(L1FileUpload.created_at.desc())
        )

        result = await session.execute(stmt)
        row = result.first()

        if row is None:
            raise ValueError(f"L1 file not found: {file_hash}")

        l1_file, original_filename = row

        registered_mime_type = l1_file.mime_type
        file_size_bytes = l1_file.file_size_bytes

    storage = LocalStorageAdapter()
    file_content = await storage.load(file_hash)

    if file_content is None:
        raise FileNotFoundError(
            f"CAS file not found: {file_hash}"
        )

    detector = MediaTypeDetector()
    detection = detector.detect(
        file_content,
        filename=original_filename,
    )

    return {
        "file_hash": file_hash,
        "original_filename": original_filename,
        "file_size_bytes": file_size_bytes,
        "content_size_bytes": len(file_content),
        "registered_mime_type": registered_mime_type,
        "detected_mime_type": detection.mime_type,
        "detected_format_type": detection.format_type,
        "detected": detection.detected,
        "detection_method": detection.detection_method,
        "mime_type_matches": (
            registered_mime_type == detection.mime_type
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="L1 CAS MediaTypeDetector test"
    )

    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        "--list",
        action="store_true",
        help="アップロード済みファイル一覧を表示",
    )

    group.add_argument(
        "--file-hash",
        help="検証対象のfile_hash",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="一覧表示件数（default: 50）",
    )

    args = parser.parse_args()

    try:
        if args.list:
            asyncio.run(list_files(args.limit))
            return

        result = asyncio.run(detect_file(args.file_hash))

        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

        if not result["detected"]:
            sys.exit(2)

    except Exception:
        logger.exception("MediaTypeDetector test failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
