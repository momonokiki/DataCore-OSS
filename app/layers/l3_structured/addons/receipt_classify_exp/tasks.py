
import asyncio

from app.celery_app import celery_app
from app.core.config import settings
from app.infrastructure.db.session import AsyncSessionLocal


@celery_app.task(
    name="tasks.classify_receipt_numeric",
    queue="parse_tasks",
)
def classify_receipt_numeric_task(context: dict) -> dict:
    """
    L3 Receipt Numeric Classification Experiment Task.

    OCR成果物を入力として、
    Numeric Span Extraction v2 と
    Numeric Classification v1 を実行し、
    独立したAddon専用テーブルに保存する。
    """

    print(
        "[Celery Worker] Receipt Numeric Classification Task "
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
            "receipt_classify_exp_status": "skipped",
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

    if "receipt_classify_exp" not in enabled:
        return {
            **context,
            "receipt_classify_exp_status": "skipped",
            "reason": "addon_disabled",
        }

    # ---------------------------------------------------------
    # 3. Addon Serviceの呼び出し
    # ---------------------------------------------------------
    from app.layers.l3_structured.addons.receipt_classify_exp.service import (
        classify_receipt_file,
    )

    async def run() -> dict:
        async with AsyncSessionLocal() as session:
            return await classify_receipt_file(
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
            "[Celery Worker] Receipt Numeric Classification "
            f"completed: {output_context}"
        )

        return output_context

    except Exception as e:
        print(
            "[Celery Worker] Receipt Numeric Classification "
            f"failed: {str(e)}"
        )
        raise

