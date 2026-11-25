# app/layers/l3_structured/addons/gpx_stay/service.py
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.l3_tools import L3Tool
from app.layers.l3_structured.addons.gpx_stay.detector import (
    DISTANCE_THRESHOLD_M,
    MAX_GAP_MINUTES,
    MIN_STAY_MINUTES,
    detect_stays,
    extract_track_points,
)
from app.layers.l3_structured.addons.gpx_stay.models import GpxStay

TOOL_NAME = "gpx_stay_extractor"
TOOL_VERSION = "gpx_stay_v1"


async def extract_gpx_stays(
    session: AsyncSession,
    file_hash: str,
    file_bytes: bytes,
) -> dict:
    """
    GPXのトラックポイントから滞在を検出し、L3テーブルへ保存する。

    検出パラメータは detector.py の冒頭の定数が正。
    再実行した場合は、同じ file_hash + tool の滞在を入れ直す
    （パラメータを調整して再実行する使い方を想定するため、
    finance の already_exists 方式ではなく置き換え方式にする）。
    """
    base = {"file_hash": file_hash}

    try:
        # 1. Tool定義の確認（トランザクション1）
        async with session.begin():
            tool = (await session.execute(
                select(L3Tool).where(L3Tool.name == TOOL_NAME)
            )).scalar_one_or_none()

            if tool is None:
                raise ValueError(f"Tool '{TOOL_NAME}' is not registered; run setup script first")

            if not tool.is_active:
                return {**base, "status": "skipped", "reason": "tool_disabled"}

            if tool.prompt_version != TOOL_VERSION:
                raise ValueError(f"Tool version mismatch for {TOOL_NAME}")

            tool_id = tool.id

        # 2. 点の抽出と滞在検出（GPXでなければ ValueError が伝播する）
        points = extract_track_points(file_bytes)
        if not points:
            return {**base, "status": "skipped", "reason": "no_track_points"}

        stays = detect_stays(points)

        # 3. 既存の滞在を消して入れ直す（トランザクション2）
        async with session.begin():
            await session.execute(
                delete(GpxStay).where(
                    GpxStay.file_hash == file_hash,
                    GpxStay.tool_id == tool_id,
                )
            )
            for index, stay in enumerate(stays):
                session.add(GpxStay(
                    id=uuid.uuid4(),
                    file_hash=file_hash,
                    tool_id=tool_id,
                    stay_index=index,
                    latitude=stay.latitude,
                    longitude=stay.longitude,
                    started_at=stay.started_at,
                    ended_at=stay.ended_at,
                    duration_seconds=stay.duration_seconds,
                    point_count=stay.point_count,
                    max_distance_m=stay.max_distance_m,
                ))

        return {
            **base,
            "status": "success",
            "point_count": len(points),
            "stay_count": len(stays),
            "parameters": {
                "distance_threshold_m": DISTANCE_THRESHOLD_M,
                "min_stay_minutes": MIN_STAY_MINUTES,
                "max_gap_minutes": MAX_GAP_MINUTES,
            },
        }

    except Exception:
        await session.rollback()
        raise
