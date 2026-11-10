
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.l3_tools import L3Tool
from app.layers.l2_extracted.models import L2Artifact

from app.layers.l3_structured.addons.yomitoku_layout import (
    TOOL_NAME as YOMITOKU_LAYOUT_TOOL_NAME,
)
from app.layers.l3_structured.addons.yomitoku_layout.models import (
    YomitokuLayoutRun,
    YomitokuLayoutLine,
)

from . import TOOL_NAME
from .models import (
    ReceiptClassifyExpRun,
    ReceiptClassifyExpLine,
    ReceiptClassifyExpSpan,
)
from .numeric_features import build_numeric_features
from .setup import PROMPT_VERSION
from .numeric_classification import build_numeric_classification


async def classify_receipt_file(
    session: AsyncSession,
    file_hash: str,
    parent_ocr_id: str | None = None,
    plugin_name: str = TOOL_NAME,
) -> dict[str, Any]:
    """Extract and classify numeric spans from YomiToku Layout lines.

    L2 OCR artifact remains the immutable source reference.
    Logical OCR lines are supplied by the yomitoku_layout addon.

    This function owns its transaction. The caller must pass a fresh session.
    """

    base = {
        "file_hash": file_hash,
        "artifact_id": parent_ocr_id,
    }

    if not parent_ocr_id:
        return {
            **base,
            "receipt_classify_exp_status": "skipped",
            "reason": "ocr_artifact_id_missing",
        }

    try:
        source_id = uuid.UUID(str(parent_ocr_id))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid OCR artifact UUID: {parent_ocr_id}"
        ) from exc

    async with session.begin():
        # ------------------------------------------------------------
        # 1. Validate source L2 OCR artifact
        # ------------------------------------------------------------
        source = await session.get(L2Artifact, source_id)

        if (
            source is None
            or source.file_hash != file_hash
            or source.artifact_type != "ocr_text"
        ):
            raise ValueError(
                "OCR source id, file_hash, or artifact_type mismatch"
            )

        # ------------------------------------------------------------
        # 2. Validate receipt_classify_exp tool
        # ------------------------------------------------------------
        tool_result = await session.execute(
            select(L3Tool).where(L3Tool.name == plugin_name)
        )
        tool = tool_result.scalar_one_or_none()

        if tool is None:
            raise ValueError(
                f"L3Tool '{plugin_name}' is not registered; "
                "run addon setup first"
            )

        if not tool.is_active:
            return {
                **base,
                "receipt_classify_exp_status": "skipped",
                "reason": "addon_tool_disabled",
            }

        if tool.prompt_version != PROMPT_VERSION:
            raise ValueError(
                f"Tool version mismatch: expected {PROMPT_VERSION}, "
                f"got {tool.prompt_version}"
            )

        # ------------------------------------------------------------
        # 3. Check existing classification run
        # ------------------------------------------------------------
        existing_result = await session.execute(
            select(ReceiptClassifyExpRun).where(
                ReceiptClassifyExpRun.source_artifact_id == source_id,
                ReceiptClassifyExpRun.tool_id == tool.id,
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing is not None:
            return {
                **base,
                "receipt_classify_exp_status": "already_exists",
                "run_id": str(existing.id),
                "row_count": existing.row_count,
                "numeric_span_count": existing.span_count,
            }

        # ------------------------------------------------------------
        # 4. Validate YomiToku Layout tool
        # ------------------------------------------------------------
        layout_tool_result = await session.execute(
            select(L3Tool).where(
                L3Tool.name == YOMITOKU_LAYOUT_TOOL_NAME
            )
        )
        layout_tool = layout_tool_result.scalar_one_or_none()

        if layout_tool is None:
            raise ValueError(
                f"L3Tool '{YOMITOKU_LAYOUT_TOOL_NAME}' "
                "is not registered; run addon setup first"
            )

        if not layout_tool.is_active:
            return {
                **base,
                "receipt_classify_exp_status": "skipped",
                "reason": "yomitoku_layout_tool_disabled",
            }

        # ------------------------------------------------------------
        # 5. Get YomiToku Layout run for the source OCR artifact
        # ------------------------------------------------------------
        layout_run_result = await session.execute(
            select(YomitokuLayoutRun).where(
                YomitokuLayoutRun.source_artifact_id == source_id,
                YomitokuLayoutRun.tool_id == layout_tool.id,
            )
        )
        layout_run = layout_run_result.scalar_one_or_none()

        if layout_run is None:
            return {
                **base,
                "receipt_classify_exp_status": "skipped",
                "reason": "yomitoku_layout_run_missing",
            }

        if layout_run.file_hash != file_hash:
            raise ValueError(
                "YomiToku Layout run file_hash does not match OCR source"
            )

        # ------------------------------------------------------------
        # 6. Get reconstructed OCR lines
        # ------------------------------------------------------------
        layout_lines_result = await session.execute(
            select(YomitokuLayoutLine)
            .where(
                YomitokuLayoutLine.run_id == layout_run.id,
                YomitokuLayoutLine.file_hash == file_hash,
            )
            .order_by(YomitokuLayoutLine.line_index)
        )
        layout_lines = layout_lines_result.scalars().all()

        if not layout_lines:
            return {
                **base,
                "receipt_classify_exp_status": "skipped",
                "reason": "yomitoku_layout_lines_empty",
            }

        structure = {
            "structure_method": "yomitoku_layout_lines_v1",
            "rows": [
                {
                    "line_index": line.line_index,
                    "row_type": "OCR_LINE",
                    "text": line.line_text,
                }
                for line in layout_lines
            ],
        }

        # ------------------------------------------------------------
        # 7. Numeric feature extraction and classification
        # ------------------------------------------------------------
        extraction = build_numeric_features(structure)
        classification = build_numeric_classification(extraction)

        # ------------------------------------------------------------
        # 8. Persist classification run
        # ------------------------------------------------------------
        run = ReceiptClassifyExpRun(
            file_hash=file_hash,
            source_artifact_id=source_id,
            tool_id=tool.id,
            extraction_method=extraction["numeric_feature_method"],
            classification_method=classification[
                "numeric_classification_method"
            ],
            row_count=classification["row_count"],
            span_count=classification["numeric_span_count"],
            classification_counts=classification["classification_counts"],
            extraction_payload=extraction,
            classification_payload=classification,
        )

        session.add(run)
        await session.flush()

        # ------------------------------------------------------------
        # 9. Persist every reconstructed line
        # ------------------------------------------------------------
        feature_rows = {
            row.get("line_index"): row
            for row in extraction.get("rows", [])
        }

        line_records: dict[int, ReceiptClassifyExpLine] = {}

        for row in classification["rows"]:
            line_index = int(row.get("line_index", 0))
            feature_row = feature_rows.get(line_index, {})

            line_record = ReceiptClassifyExpLine(
                run_id=run.id,
                line_index=line_index,
                row_type=str(row.get("row_type") or "OCR_LINE"),
                line_text=str(row.get("text", "")),
                numeric_features=feature_row.get(
                    "numeric_features", {}
                ),
                numeric_classifications=list(
                    row.get("numeric_classifications", [])
                ),
            )

            session.add(line_record)
            line_records[line_index] = line_record

        await session.flush()

        # ------------------------------------------------------------
        # 10. Persist classified numeric spans
        # ------------------------------------------------------------
        span_records: list[ReceiptClassifyExpSpan] = []

        for row in classification["rows"]:
            line_index = int(row.get("line_index", 0))
            line_record = line_records[line_index]

            for item in row.get("numeric_classifications", []):
                span_records.append(
                    ReceiptClassifyExpSpan(
                        run_id=run.id,
                        line_id=line_record.id,
                        line_index=line_index,
                        span_index=int(item["span_index"]),
                        start_offset=int(item["start"]),
                        end_offset=int(item["end"]),
                        span_text=str(item["text"]),
                        label=str(item["label"]),
                        evidence=list(item.get("evidence", [])),
                        raw_payload=item,
                    )
                )

        if span_records:
            session.add_all(span_records)

        await session.flush()

        result = {
            **base,
            "receipt_classify_exp_status": "completed",
            "run_id": str(run.id),
            "tool_id": str(tool.id),
            "layout_run_id": str(layout_run.id),
            "row_count": run.row_count,
            "numeric_span_count": run.span_count,
            "classification_counts": run.classification_counts,
        }

    return result

