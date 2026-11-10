from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.l3_tools import L3Tool
from app.layers.l2_extracted.models import L2Artifact

from . import TOOL_NAME
from .layout import build_layout
from .models import YomitokuLayoutLine, YomitokuLayoutRun
from .setup import PROMPT_VERSION


DEFAULT_LINE_TOLERANCE_RATIO = 0.45


def _get_words(source: L2Artifact) -> list[dict[str, Any]]:
    """L2 Artifactのbounding_boxからOCR wordsを取得する。"""
    bounding_box = source.bounding_box

    if not isinstance(bounding_box, dict):
        return []

    words = bounding_box.get("words")

    if not isinstance(words, list):
        return []

    for index, word in enumerate(words):
        if not isinstance(word, dict):
            raise ValueError(
                f"Invalid OCR word at bounding_box.words[{index}]: "
                "expected object"
            )

    return words


def _required_float(
    value: Any,
    field_name: str,
) -> float:
    """必須座標をfloatに変換する。Noneや不正値は許可しない。"""
    if value is None:
        raise ValueError(
            f"Required layout coordinate is missing: {field_name}"
        )

    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            f"Invalid layout coordinate {field_name}: {value!r}"
        ) from exc

    import math

    if not math.isfinite(result):
        raise ValueError(
            f"Non-finite layout coordinate {field_name}: {value!r}"
        )

    return result


def _build_line_bbox(
    words: list[dict[str, Any]],
) -> dict[str, float]:
    """行を構成する全単語の外接矩形を計算する。"""
    geometries = []

    for index, word in enumerate(words):
        geometry = word.get("_layout")

        if not isinstance(geometry, dict):
            raise ValueError(
                f"Layout geometry missing in line word[{index}]"
            )

        geometries.append(
            {
                key: _required_float(
                    geometry.get(key),
                    f"word[{index}].{key}",
                )
                for key in ("x_min", "x_max", "y_min", "y_max")
            }
        )

    if not geometries:
        raise ValueError("Cannot build line bbox without words")

    return {
        "x_min": min(item["x_min"] for item in geometries),
        "x_max": max(item["x_max"] for item in geometries),
        "y_min": min(item["y_min"] for item in geometries),
        "y_max": max(item["y_max"] for item in geometries),
    }


def _build_blocks(
    words: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """行を構成するOCR単語をBlockとして保存する。"""
    blocks: list[dict[str, Any]] = []

    for index, word in enumerate(words):
        geometry = word.get("_layout")

        if not isinstance(geometry, dict):
            raise ValueError(
                f"Layout geometry missing in line word[{index}]"
            )

        source_index = word.get("_source_index")

        if source_index is None:
            raise ValueError(
                f"Source word index missing in line word[{index}]"
            )

        blocks.append(
            {
                "source_index": int(source_index),
                "text": str(word.get("content", "")),
                "geometry": geometry,
                "source_word": {
                    key: value
                    for key, value in word.items()
                    if key not in {"_layout", "_source_index"}
                },
            }
        )

    return blocks


async def build_yomitoku_layout(
    session: AsyncSession,
    file_hash: str,
    parent_ocr_id: str | None = None,
    plugin_name: str = TOOL_NAME,
) -> dict[str, Any]:
    """既存のL2 YomiToku OCR Artifactから論理行を再構成する。

    L2 Artifactは変更しない。
    OCR word geometryを読み込み、レイアウトを計算してL3に保存する。

    この関数がトランザクションを管理する。
    呼び出し側は新しいAsyncSessionを渡すこと。
    """
    base = {
        "file_hash": file_hash,
        "artifact_id": parent_ocr_id,
    }

    if not parent_ocr_id:
        return {
            **base,
            "yomitoku_layout_status": "skipped",
            "reason": "ocr_artifact_id_missing",
        }

    try:
        source_id = uuid.UUID(str(parent_ocr_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(
            f"Invalid OCR artifact UUID: {parent_ocr_id}"
        ) from exc

    async with session.begin():
        source = await session.get(
            L2Artifact,
            source_id,
        )

        if (
            source is None
            or source.file_hash != file_hash
            or source.artifact_type != "ocr_text"
        ):
            raise ValueError(
                "OCR source id, file_hash, or artifact_type mismatch"
            )

        words = _get_words(source)

        if not words:
            return {
                **base,
                "yomitoku_layout_status": "skipped",
                "reason": "ocr_word_geometry_missing",
            }

        tool_result = await session.execute(
            select(L3Tool).where(
                L3Tool.name == plugin_name
            )
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
                "yomitoku_layout_status": "skipped",
                "reason": "addon_tool_disabled",
            }

        if tool.prompt_version != PROMPT_VERSION:
            raise ValueError(
                f"Tool version mismatch: expected {PROMPT_VERSION}, "
                f"got {tool.prompt_version}"
            )

        existing_result = await session.execute(
            select(YomitokuLayoutRun).where(
                YomitokuLayoutRun.source_artifact_id == source_id,
                YomitokuLayoutRun.tool_id == tool.id,
            )
        )

        existing = existing_result.scalar_one_or_none()

        if existing is not None:
            return {
                **base,
                "yomitoku_layout_status": "already_exists",
                "run_id": str(existing.id),
                "tool_id": str(existing.tool_id),
                "line_count": existing.line_count,
                "word_count": existing.word_count,
            }

        config = (
            tool.config
            if isinstance(tool.config, dict)
            else {}
        )

        line_tolerance_ratio = float(
            config.get(
                "line_tolerance_ratio",
                DEFAULT_LINE_TOLERANCE_RATIO,
            )
        )

        layout = build_layout(
            words,
            line_tolerance_ratio=line_tolerance_ratio,
        )

        layout_version = str(
            config.get("layout_version", "geometry_v1")
        )

        run = YomitokuLayoutRun(
            file_hash=file_hash,
            source_artifact_id=source_id,
            tool_id=tool.id,
            layout_method=str(layout["layout_method"]),
            layout_version=layout_version,
            line_tolerance_ratio=line_tolerance_ratio,
            text_direction=str(layout["text_direction"]),
            line_axis=str(layout["line_axis"]),
            inline_axis=str(layout["inline_axis"]),
            median_cross_axis_size=_required_float(
                layout["median_cross_axis_size"],
                "median_cross_axis_size",
            ),
            line_tolerance_pixels=_required_float(
                layout["line_tolerance_pixels"],
                "line_tolerance_pixels",
            ),
            word_count=int(layout["word_count"]),
            line_count=int(layout["line_count"]),
            direction_inference=layout.get(
                "direction_inference",
                {},
            ),
            parameters={
                "line_tolerance_ratio": line_tolerance_ratio,
                "layout_method": layout["layout_method"],
                "layout_version": layout_version,
            },
            result_payload=layout,
        )

        session.add(run)
        await session.flush()

        line_records: list[YomitokuLayoutLine] = []

        for row in layout.get("rows", []):
            row_words = row.get("words", [])

            if not row_words:
                raise ValueError(
                    f"Layout line {row.get('line_index')} has no words"
                )

            line_records.append(
                YomitokuLayoutLine(
                    file_hash=file_hash,
                    run_id=run.id,
                    line_index=int(row["line_index"]),
                    line_text=str(row.get("text", "")),
                    center_x=_required_float(
                        row.get("center_x"),
                        f"line[{row.get('line_index')}].center_x",
                    ),
                    center_y=_required_float(
                        row.get("center_y"),
                        f"line[{row.get('line_index')}].center_y",
                    ),
                    line_center=_required_float(
                        row.get("line_center"),
                        f"line[{row.get('line_index')}].line_center",
                    ),
                    bbox=_build_line_bbox(row_words),
                    blocks=_build_blocks(row_words),
                )
            )

        if len(line_records) != int(layout["line_count"]):
            raise ValueError(
                "Layout line_count does not match generated line records"
            )

        session.add_all(line_records)
        await session.flush()

        result = {
            **base,
            "yomitoku_layout_status": "completed",
            "run_id": str(run.id),
            "tool_id": str(tool.id),
            "layout_method": run.layout_method,
            "text_direction": run.text_direction,
            "line_count": run.line_count,
            "word_count": run.word_count,
        }

    return result