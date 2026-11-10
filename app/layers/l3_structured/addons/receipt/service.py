import uuid

import app.db_all_models  # register existing relationship targets
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.infrastructure.db.models.l3_tools import L3Tool
from app.layers.l2_extracted.models import L2Artifact

from .models import ReceiptTotal, ReceiptItem
from .parser import (
    PROMPT_VERSION,
    parse_receipt_header,
    parse_receipt_items,
)
from .schemas import ReceiptData

DEFAULT_TOOL_NAME = "receipt_ollama_two_step_v2"


async def parse_receipt_file(
    session: AsyncSession,
    file_hash: str,
    parent_ocr_id: str | None = None,
    plugin_name: str = DEFAULT_TOOL_NAME,
) -> dict:
    """
    OCR成果物をStep1（ヘッダー）とStep2（品目）に分けて構造化し、
    合計テーブルと品目テーブルへ保存する。

    - 呼び出し側は新規セッションを渡すこと
    - この関数がcommit / rollbackを所有する
    - 例外は握りつぶさずCeleryへ伝播させる
    """
    base = {
        "file_hash": file_hash,
        "artifact_id": parent_ocr_id,
    }

    try:
        if parent_ocr_id is None:
            return {
                **base,
                "receipt_status": "skipped",
                "reason": "ocr_artifact_id_missing",
            }

        source_id = uuid.UUID(str(parent_ocr_id))

        # ------------------------------------------------------------------
        # Step 0: OCR成果物・パーサー設定・冪等性の確認
        # ------------------------------------------------------------------
        async with session.begin():
            source = await session.get(L2Artifact, source_id)

            if (
                source is None
                or source.file_hash != file_hash
                or source.artifact_type != "ocr_text"
            ):
                raise ValueError(
                    "OCR source id, file hash or artifact type mismatch"
                )

            if not source.content_text or not source.content_text.strip():
                return {
                    **base,
                    "receipt_status": "skipped",
                    "reason": "ocr_text_empty",
                }

            tool = (
                await session.execute(
                    select(L3Tool).where(L3Tool.name == plugin_name)
                )
            ).scalar_one_or_none()

            if tool is None:
                raise ValueError(
                    "Receipt parser tool is not registered; run setup first"
                )

            if not tool.is_active:
                return {
                    **base,
                    "receipt_status": "skipped",
                    "reason": "parser_disabled",
                }

            if tool.prompt_version != PROMPT_VERSION:
                raise ValueError("Parser prompt version mismatch")

            tool_id = tool.id
            model_name = tool.model_name
            text = source.content_text

            query = select(ReceiptTotal).where(
                ReceiptTotal.source_artifact_id == source_id,
                ReceiptTotal.parser_tool_id == tool_id,
            )

            existing = (
                await session.execute(query)
            ).scalar_one_or_none()

            if existing:
                return {
                    **base,
                    "receipt_status": "already_exists",
                    "receipt_id": str(existing.id),
                }

        # ------------------------------------------------------------------
        # Step 1: レシート判定 + 店舗 + 日時 + 金額
        # ------------------------------------------------------------------
        header = await parse_receipt_header(
            text=text,
            base_url=settings.OLLAMA_BASE_URL,
            model_name=model_name,
        )

        if not header.is_receipt:
            return {
                **base,
                "receipt_status": "skipped",
                "reason": "not_receipt",
            }

        # --------------------------------------------------------------        # ------------------------------------------------------------------
        # Step 2: 商品明細のみ抽出
        # ------------------------------------------------------------------
        items_result = await parse_receipt_items(
            text=text,
            base_url=settings.OLLAMA_BASE_URL,
            model_name=model_name,
        )

        parsed = ReceiptData(
            header=header,
            items=items_result.items,
        )

        # ------------------------------------------------------------------
        # DB保存用とJSON保存用を分ける
        # ------------------------------------------------------------------
        header_for_db = parsed.header.model_dump()
        header_for_payload = parsed.header.model_dump(mode="json")

        item_data_list_for_db = [
            item.model_dump()
            for item in parsed.items
        ]

        item_data_list_for_payload = [
            item.model_dump(mode="json")
            for item in parsed.items
        ]

        reasons = parsed.review_reasons

        # ------------------------------------------------------------------
        # Step 3: OCR成果物を再確認し、合計・品目を同一トランザクションで保存
        # ------------------------------------------------------------------
        async with session.begin():
            source = (
                await session.execute(
                    select(L2Artifact)
                    .where(L2Artifact.id == source_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()

            if (
                source is None
                or source.file_hash != file_hash
                or source.artifact_type != "ocr_text"
                or source.content_text != text
            ):
                raise ValueError(
                    "OCR source changed or disappeared during inference"
                )

            existing = (
                await session.execute(query)
            ).scalar_one_or_none()

            if existing:
                return {
                    **base,
                    "receipt_status": "already_exists",
                    "receipt_id": str(existing.id),
                }

            receipt = ReceiptTotal(
                id=uuid.uuid4(),
                file_hash=file_hash,
                source_artifact_id=source_id,
                parser_tool_id=tool_id,
                needs_review=bool(reasons),
                review_reasons=reasons,
                raw_payload={
                    "header": header_for_payload,
                    "items": item_data_list_for_payload,
                },
                **{
                    key: value
                    for key, value in header_for_db.items()
                    if key != "is_receipt"
                },
            )

            receipt.items = [
                ReceiptItem(
                    line_number=line_number,
                    **item_data,
                )
                for line_number, item_data in enumerate(
                    item_data_list_for_db,
                    start=1,
                )
            ]

            session.add(receipt)
            await session.flush()

            receipt_id = str(receipt.id)

        return {
            **base,
            "receipt_status": "success",
            "receipt_id": receipt_id,
            "receipt_item_count": len(parsed.items),
            "needs_review": bool(reasons),
        }

    except Exception:
        await session.rollback()
        raise
