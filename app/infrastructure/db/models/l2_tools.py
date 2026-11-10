import uuid
from typing import Any, Optional
from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin


class L2Tool(Base, TimestampMixin):
    """
    L2抽出・生成ツールのマスターテーブル
    OCRエンジン、埋め込みモデル、レイアウト解析器などの仕様・設定を保持します。
    """

    __tablename__ = "l2_tools"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="ツール名・識別子 (例: openai_embed_v3_small, bge_m3_binary)",
    )
    tool_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="ツールの種類 (embedding, ocr, layout_parser, chunker など)",
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="ツールの概要説明",
    )

    # ★ ベクトル出力・精度に関する仕様（Embeddingツールの場合に設定）
    output_dim: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="出力ベクトルの次元数 (例: 384, 768, 1536)",
    )
    precision_type: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True,
        comment="ベクトルの精度・データ形式 (float32, float16, binary, int8 など)",
    )
    
    # 実行・モデル詳細情報
    model_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="使用モデル名 (例: text-embedding-3-small, Japanese-CLIP)",
    )
    model_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="モデルやツールのバージョン (例: v1.0, 0.4.1)",
    )
    config_json: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="その他の設定・量子化閾値・プロンプトテンプレート等",
    )