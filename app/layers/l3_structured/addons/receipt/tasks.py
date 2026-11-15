
import asyncio

from app.celery_app import celery_app
from app.core.config import settings
from app.infrastructure.db.session import AsyncSessionLocal


@celery_app.task(
    name="tasks.parse_file",
    queue="parse_tasks",
)
def parse_file_task(context: dict) -> dict:
    """L3レシート構造化タスク"""

    if not isinstance(context, dict) or not context.get("file_hash"):
        raise ValueError(
            "L3 requires a context dict with file_hash"
        )

    enabled = {
        name.strip()
        for name in settings.ENABLED_L3_ADDONS.split(",")
        if name.strip()
    }

    if "receipt" not in enabled:
        return {
            **context,
            "receipt_status": "skipped",
            "reason": "receipt_addon_disabled",
        }

    # Addon Serviceは有効時にのみ読み込む
    from app.layers.l3_structured.addons.receipt.service import (
        parse_receipt_file,
    )

    async def run() -> dict:
        async with AsyncSessionLocal() as session:
            return await parse_receipt_file(
                session=session,
                file_hash=str(context["file_hash"]),
                parent_ocr_id=context.get("artifact_id"),
            )

    return {
        **context,
        **asyncio.run(run()),
    }

