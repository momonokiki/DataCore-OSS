from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base, TimestampMixin


class ReceiptClassifyExpRun(Base, TimestampMixin):
    """One immutable numeric-analysis result for an OCR artifact/tool pair."""

    __tablename__ = "addon_l3_receipt_classify_exp_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    file_hash: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("l1_files.file_hash", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("l2_artifacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("l3_tools.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    extraction_method: Mapped[str] = mapped_column(String(100), nullable=False)
    classification_method: Mapped[str] = mapped_column(String(100), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    span_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    classification_counts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    extraction_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    classification_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    lines: Mapped[list["ReceiptClassifyExpLine"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True,
    )
    spans: Mapped[list["ReceiptClassifyExpSpan"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "source_artifact_id",
            "tool_id",
            name="uq_receipt_classify_exp_source_tool",
        ),
        Index(
            "ix_receipt_classify_exp_runs_file_created",
            "file_hash",
            "created_at",
        ),
    )


class ReceiptClassifyExpSpan(Base, TimestampMixin):
    """Queryable projection of each classified numeric span."""

    __tablename__ = "addon_l3_receipt_classify_exp_spans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "addon_l3_receipt_classify_exp_runs.id", ondelete="CASCADE"
        ),
        nullable=False,
        index=True,
    )
    line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("addon_l3_receipt_classify_exp_lines.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    line_index: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    span_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    span_text: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    evidence: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # None = not reviewed, True = correct, False = incorrect.
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)

    run: Mapped[ReceiptClassifyExpRun] = relationship(back_populates="spans")

    __table_args__ = (
        UniqueConstraint("run_id", "line_index", "span_index", name="uq_receipt_classify_exp_span"),
        Index("ix_receipt_classify_exp_spans_label_text", "label", "span_text"),
    )


class ReceiptClassifyExpLine(Base, TimestampMixin):
    """Full source OCR line plus its extraction/classification payloads."""

    __tablename__ = "addon_l3_receipt_classify_exp_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("addon_l3_receipt_classify_exp_runs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    line_index: Mapped[int] = mapped_column(Integer, nullable=False)
    row_type: Mapped[str] = mapped_column(String(32), nullable=False, default="OCR_LINE")
    line_text: Mapped[str] = mapped_column(String, nullable=False)
    numeric_features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    numeric_classifications: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    # Human review note for the whole OCR line; intentionally short/free text.
    evaluation_note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    run: Mapped[ReceiptClassifyExpRun] = relationship(back_populates="lines")

    __table_args__ = (
        UniqueConstraint("run_id", "line_index", name="uq_receipt_classify_exp_line"),
        Index("ix_receipt_classify_exp_lines_text", "line_text"),
    )
