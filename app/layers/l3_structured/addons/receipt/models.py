from __future__ import annotations
import uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.infrastructure.db.base import Base, TimestampMixin

class ReceiptTotal(Base, TimestampMixin):
    __tablename__ = "addon_l3_receipt_totals"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_hash: Mapped[str] = mapped_column(String(64), ForeignKey("l1_files.file_hash", ondelete="CASCADE"), index=True)
    source_artifact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("l2_artifacts.id", ondelete="CASCADE"), index=True)
    parser_tool_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("l3_tools.id", ondelete="RESTRICT"), index=True)
    store_name: Mapped[str | None] = mapped_column(String(255), index=True)
    transaction_date: Mapped[date | None] = mapped_column(Date, index=True)
    transaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    currency: Mapped[str] = mapped_column(String(3), default="JPY",nullable=True)
    subtotal_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    payment_method: Mapped[str | None] = mapped_column(String(100))
    needs_review: Mapped[bool] = mapped_column(Boolean, default=True)
    review_reasons: Mapped[list] = mapped_column(JSONB, default=list)
    raw_payload: Mapped[dict] = mapped_column(JSONB)

    # ---- 承認管理 (人間による確認済みフラグ。needs_review とは独立に運用する) ----
    # 未承認 = approved_at IS NULL / 承認済み = approved_at IS NOT NULL
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="承認したユーザーID (未承認時はNULL)",
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="承認日時 (未承認時はNULL)",
    )

    items: Mapped[list[ReceiptItem]] = relationship(back_populates="receipt", cascade="all, delete-orphan", passive_deletes=True)
    __table_args__ = (UniqueConstraint("source_artifact_id", "parser_tool_id", name="uq_receipt_source_parser"),)

class ReceiptItem(Base, TimestampMixin):
    __tablename__ = "addon_l3_receipt_items"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    receipt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("addon_l3_receipt_totals.id", ondelete="CASCADE"), index=True)
    line_number: Mapped[int] = mapped_column(Integer)
    item_name: Mapped[str] = mapped_column(String(512), index=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    line_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), comment="百分率: 8, 10")
    raw_text: Mapped[str | None] = mapped_column(String(2048))
    receipt: Mapped[ReceiptTotal] = relationship(back_populates="items")
    __table_args__ = (
        UniqueConstraint("receipt_id", "line_number", name="uq_receipt_item_line"),
        CheckConstraint("line_number > 0", name="ck_receipt_line_positive"),
    )
