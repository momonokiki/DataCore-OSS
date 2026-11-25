# app/layers/l3_structured/addons/gpx_stay/tasks.py
import asyncio

from app.celery_app import celery_app
from app.infrastructure.db.session import AsyncSessionLocal
from app.infrastructure.storage import LocalStorageAdapter
from app.layers.l3_structured.addons.gpx_stay.service import extract_gpx_stays


@celery_app.task(
    name="tasks.extract_gpx_stays",
    queue="parse_tasks",
)
def extract_gpx_stays_task(file_hash: str) -> dict:
    """
    GPX専用ルート。
    L1ストレージからGPXファイルを直接ロードし、
    滞在検出を行ってL3ドメインテーブルへ保存する。
    パイプラインの自動選択は行わず、利用者が明示的に起動する。
    """
    print(
        "[Celery Worker] GPX Stay Extraction Task "
        f"triggered for hash: {file_hash}"
    )

    storage = LocalStorageAdapter()

    async def fetch_and_extract():
        file_bytes = await storage.load(str(file_hash))

        if not file_bytes:
            return {
                "file_hash": file_hash,
                "status": "skipped",
                "reason": "l1_binary_not_found",
            }

        async with AsyncSessionLocal() as session:
            return await extract_gpx_stays(
                session=session,
                file_hash=str(file_hash),
                file_bytes=file_bytes,
            )

    try:
        result = asyncio.run(fetch_and_extract())

        print(
            "[Celery Worker] GPX Stay Task completed. "
            f"Output: {result}"
        )

        return result

    except Exception as e:
        print(
            "[Celery Worker] Fatal error in GPX Stay Task: "
            f"{str(e)}"
        )
        raise
