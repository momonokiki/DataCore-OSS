import uuid
from typing import Any, Optional
from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin


class L3Tool(Base, TimestampMixin):
    """L3専用ツール/パーサーマスタ (LLM構造化プロンプト, ドメイン用ルールエンジン等)"""

    __tablename__ = "l3_tools"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        comment="識別名 (例: receipt_parser_qwen2.5_v1, invoice_extractor_gpt4o_v2)",
    )
    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="使用基盤LLM/エンジン (例: qwen2.5:7b, gpt-4o-mini, local_rule_v1)",
    )
    prompt_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="プロンプトやパースルールのバージョン",
    )
    config: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="システムプロンプト、Temperature、JSON Schema定義等",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="有効フラグ",
    )