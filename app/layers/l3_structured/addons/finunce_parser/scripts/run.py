import argparse
import asyncio
import json
import os
from app.infrastructure.db.session import AsyncSessionLocal
from app.layers.l3_structured.addons.finunce_parser.service import parse_financial_csv

async def run(args):
    # 1. 指定されたローカルのテストCSVファイルをバイナリモードで読み込む
    if not os.path.exists(args.csv_path):
        print(f"Error: Target CSV file not found at {args.csv_path}")
        return

    with open(args.csv_path, "rb") as f:
        file_bytes = f.read()

    print(f"Loading local CSV: {args.csv_path} ({len(file_bytes)} bytes)")
    print(f"Executing finance_parser for file_hash: {args.file_hash}...")

    # 2. 非同期セッションの生成とサービス関数の実行
    async with AsyncSessionLocal() as session:
        result = await parse_financial_csv(
            session=session,
            file_hash=args.file_hash,
            file_bytes=file_bytes
        )

    # 3. 解析・登録結果を整形して出力
    print("\n--- Execution Result ---")
    print(json.dumps(result, ensure_ascii=False, indent=2))

def main():
    parser = argparse.ArgumentParser(description="Debug CLI script for Kakeisys Finance Parser Addon")
    parser.add_argument("--csv-path", required=True, help="Path to the local test CSV file")
    parser.add_argument("--file-hash", required=True, help="Mock L1 file hash for identification")
    
    asyncio.run(run(parser.parse_args()))

if __name__ == "__main__":
    main()

