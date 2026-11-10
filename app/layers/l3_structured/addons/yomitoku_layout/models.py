
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base, TimestampMixin


class YomitokuLayoutRun(Base, TimestampMixin):
    """One immutable layout reconstruction run for an OCR artifact."""

    __tablename__ = "addon_l3_yomitoku_layout_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    file_hash: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("l1_files.file_hash", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="対象ファイルのSHA-256ハッシュ",
    )

    source_artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("l2_artifacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="入力元L2 OCR artifact ID",
    )

    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("l3_tools.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="実行に使用したL3Tool ID",
    )

    layout_method: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="レイアウト再構成方式",
    )

    layout_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="レイアウトアルゴリズムのバージョン",
    )

    line_tolerance_ratio: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="行・列グルーピング許容値の倍率",
    )

    text_direction: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="推定文字方向: horizontal / vertical",
    )

    line_axis: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="行・列のグルーピング軸: x / y",
    )

    inline_axis: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="行・列内の並び順軸: x / y",
    )

    median_cross_axis_size: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="グルーピング軸に直交するwordサイズの中央値",
    )

    line_tolerance_pixels: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="グルーピング許容距離（ピクセル）",
    )

    word_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="入力OCR word数",
    )

    line_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="再構成された行・列数",
    )

    direction_inference: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="文字方向推定の詳細",
    )

    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="再現用の実行パラメータ",
    )

    result_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="レイアウト処理結果の付加情報",
    )

    lines: Mapped[list["YomitokuLayoutLine"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        # 同一のL2 Artifactに同一のL3Toolを
        # 二重実行・二重登録できないようにする。
        UniqueConstraint(
            "source_artifact_id",
            "tool_id",
            name="uq_yomitoku_layout_run_source_tool",
        ),
        Index(
            "ix_yomitoku_layout_runs_file_created",
            "file_hash",
            "created_at",
        ),
        Index(
            "ix_yomitoku_layout_runs_source_tool",
            "source_artifact_id",
            "tool_id",
        ),
    )


class YomitokuLayoutLine(Base, TimestampMixin):
    """One reconstructed OCR row or column."""

    __tablename__ = "addon_l3_yomitoku_layout_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    file_hash: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("l1_files.file_hash", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="対象ファイルのSHA-256ハッシュ",
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "addon_l3_yomitoku_layout_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
        comment="対応するレイアウト実行ID",
    )

    line_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="実行内の行・列番号",
    )

    line_text: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="再構成された行・列のテキスト",
    )

    center_x: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="行・列の中心X座標",
    )

    center_y: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="行・列の中心Y座標",
    )

    line_center: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="グルーピング軸上の中心座標",
    )

    bbox: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="構成wordから計算した行・列全体の外接矩形",
    )

    blocks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="行・列を構成する元OCR word情報",
    )

    run: Mapped[YomitokuLayoutRun] = relationship(
        back_populates="lines",
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "line_index",
            name="uq_yomitoku_layout_line",
        ),
        Index(
            "ix_yomitoku_layout_lines_file_text",
            "file_hash",
            "line_text",
        ),
    )
