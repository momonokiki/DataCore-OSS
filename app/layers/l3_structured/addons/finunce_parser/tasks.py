
import asyncio

from celery import Celery

from app.celery_app import celery_app
from app.infrastructure.storage import LocalStorageAdapter
from app.infrastructure.db.session import AsyncSessionLocal
from app.layers.l3_structured.addons.finunce_parser.service import (
    parse_financial_csv,
)


@celery_app.task(
    name="tasks.parse_finance_csv",
    queue="parse_tasks",
)
def parse_finance_csv_task(file_hash: str) -> dict:
    """
    【金融明細専用ルート：第0走者】
    L1ストレージから金融機関CSVファイルを直接ロードし、
    確定的パーサ群（JCB / ゆうちょ銀行）に投入してL3ドメインテーブルへ保存する。
    """

    print(
        "[Celery Worker] Finance CSV Parsing Task "
        f"triggered for hash: {file_hash}"
    )

    # CASから物理バイナリデータを取得
    storage = LocalStorageAdapter()

    async def fetch_and_parse():
        file_bytes = await storage.load(str(file_hash))

        if not file_bytes:
            return {
                "file_hash": file_hash,
                "status": "skipped",
                "reason": "l1_binary_not_found",
            }

        async with AsyncSessionLocal() as session:
            return await parse_financial_csv(
                session=session,
                file_hash=str(file_hash),
                file_bytes=file_bytes,
            )

    try:
        result = asyncio.run(fetch_and_parse())

        print(
            "[Celery Worker] Finance CSV Task completed. "
            f"Output: {result}"
        )

        return result

    except Exception as e:
        print(
            "[Celery Worker] Fatal error in Finance CSV Task: "
            f"{str(e)}"
        )
        raise

