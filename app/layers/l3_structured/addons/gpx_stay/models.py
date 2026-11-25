# app/layers/l3_structured/addons/gpx_stay/models.py
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin


class GpxStay(Base, TimestampMixin):
    """L3 GPX滞在（1ファイルから複数件できる）"""
    __tablename__ = "addon_l3_gpx_stays"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)  # L1ストレージとの紐付け
    tool_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("l3_tools.id", ondelete="RESTRICT"), index=True)

    stay_index: Mapped[int] = mapped_column(Integer)  # ファイル内での滞在の順序

    # 滞在の重心。Metabaseの地図で自動認識されるよう latitude / longitude と命名する
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int] = mapped_column(Integer)

    point_count: Mapped[int] = mapped_column(Integer)        # 滞在に所属した点の数
    max_distance_m: Mapped[float] = mapped_column(Float)     # 重心から最も離れた所属点までの距離
