
import asyncio

from app.celery_app import celery_app
from app.core.config import settings
from app.infrastructure.db.session import AsyncSessionLocal


@celery_app.task(
    name="tasks.reconstruct_yomitoku_layout",
    queue="parse_tasks",
)
def reconstruct_yomitoku_layout_task(context: dict) -> dict:
    """
    L2 YomiToku OCR Artifactからword geometryを読み込み、
    論理行・列を再構成してL3 addon専用テーブルに保存する。
    """

    print(
        "[Celery Worker] YomiToku Layout Task "
        f"received: {context}"
    )

    # ---------------------------------------------------------
    # 1. 入力コンテキスト検証
    # ---------------------------------------------------------
    if not isinstance(context, dict):
        raise ValueError(
            f"Expected dict context, got: {type(context)}"
        )

    file_hash = context.get("file_hash")
    ocr_artifact_id = context.get("artifact_id")

    if not file_hash:
        raise ValueError(
            f"Missing file_hash in context: {context}"
        )

    if not ocr_artifact_id:
        return {
            **context,
            "yomitoku_layout_status": "skipped",
            "reason": "ocr_artifact_id_missing",
        }

    # ---------------------------------------------------------
    # 2. Addon有効状態の確認
    # ---------------------------------------------------------
    enabled = {
        name.strip()
        for name in settings.ENABLED_L3_ADDONS.split(",")
        if name.strip()
    }

    if "yomitoku_layout" not in enabled:
        return {
            **context,
            "yomitoku_layout_status": "skipped",
            "reason": "addon_disabled",
        }

    # ---------------------------------------------------------
    # 3. Addon Serviceの呼び出し
    # ---------------------------------------------------------
    from app.layers.l3_structured.addons.yomitoku_layout.service import (
        build_yomitoku_layout,
    )

    async def run() -> dict:
        async with AsyncSessionLocal() as session:
            return await build_yomitoku_layout(
                session=session,
                file_hash=str(file_hash),
                parent_ocr_id=str(ocr_artifact_id),
            )

    # ---------------------------------------------------------
    # 4. 非同期Service実行
    # ---------------------------------------------------------
    try:
        result = asyncio.run(run())

        output_context = {
            **context,
            **result,
        }

        print(
            "[Celery Worker] YomiToku Layout "
            f"completed: {output_context}"
        )

        return output_context

    except Exception as e:
        print(
            "[Celery Worker] YomiToku Layout "
            f"failed: {str(e)}"
        )
        raise

