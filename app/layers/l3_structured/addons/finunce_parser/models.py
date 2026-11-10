from __future__ import annotations
import uuid
from datetime import date
from decimal import Decimal
from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, UniqueConstraint, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.infrastructure.db.base import Base, TimestampMixin

class AccountStatement(Base, TimestampMixin):
    """L3 金融明細書（親テーブル）"""
    __tablename__ = "addon_l3_kakeibo_statements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)  # L1ストレージとの紐付け
    parser_tool_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("l3_tools.id", ondelete="RESTRICT"), index=True)
    
    account_id: Mapped[str] = mapped_column(String(50), index=True)             # 例: 'jcb_card', 'yucho_bank'
    account_number: Mapped[str | None] = mapped_column(String(100), index=True) # マスクされた口座/カード番号
    total_records: Mapped[int] = mapped_column(Integer)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    raw_header: Mapped[dict] = mapped_column(JSON)  # CSVヘッダーのメタデータ

    transactions: Mapped[list[StatementTransaction]] = relationship(
        back_populates="statement", cascade="all, delete-orphan", passive_deletes=True
    )

class StatementTransaction(Base, TimestampMixin):
    """L3 取引明細行（子テーブル）"""
    __tablename__ = "addon_l3_kakeibo_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    statement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("addon_l3_kakeibo_statements.id", ondelete="CASCADE"), index=True)
    
    row_index: Mapped[int] = mapped_column(Integer)
    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    description: Mapped[str] = mapped_column(String(512), index=True)
    category_raw: Mapped[str | None] = mapped_column(String(100))
    raw_row: Mapped[dict] = mapped_column(JSON)  # 元のCSV1行分の生データ

    statement: Mapped[AccountStatement] = relationship(back_populates="transactions")

    __table_args__ = (
        UniqueConstraint("statement_id", "row_index", name="uq_kakeibo_statement_row"),
    )

