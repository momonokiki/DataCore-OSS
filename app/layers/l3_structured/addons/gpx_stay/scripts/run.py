# app/layers/l3_structured/addons/gpx_stay/scripts/run.py
import argparse
import asyncio
import json
import os

from app.infrastructure.db.session import AsyncSessionLocal
from app.layers.l3_structured.addons.gpx_stay.service import extract_gpx_stays


async def run(args):
    # 1. 指定されたローカルのGPXファイルをバイナリモードで読み込む
    if not os.path.exists(args.gpx_path):
        print(f"Error: Target GPX file not found at {args.gpx_path}")
        return

    with open(args.gpx_path, "rb") as f:
        file_bytes = f.read()

    print(f"Loading local GPX: {args.gpx_path} ({len(file_bytes)} bytes)")
    print(f"Executing gpx_stay for file_hash: {args.file_hash}...")

    # 2. 非同期セッションの生成とサービス関数の実行
    async with AsyncSessionLocal() as session:
        result = await extract_gpx_stays(
            session=session,
            file_hash=args.file_hash,
            file_bytes=file_bytes,
        )

    # 3. 検出・登録結果を整形して出力
    print("\n--- Execution Result ---")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Debug CLI script for GPX Stay Addon")
    parser.add_argument("--gpx-path", required=True, help="Path to the local test GPX file")
    parser.add_argument("--file-hash", required=True, help="L1 file hash for identification")

    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
