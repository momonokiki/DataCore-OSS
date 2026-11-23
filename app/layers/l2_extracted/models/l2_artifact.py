
import uuid
from typing import TYPE_CHECKING, Any, List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID, BIT
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType

from app.infrastructure.db.base import Base, TimestampMixin


class HalfVector(UserDefinedType):
    """SQLAlchemy custom type for pgvector halfvec (16-bit float vector)."""

    cache_ok = True

    def __init__(self, dim: Optional[int] = None):
        self.dim = dim

    def get_col_spec(self, **kw: Any) -> str:
        if self.dim:
            return f"HALFVEC({self.dim})"
        return "HALFVEC"


if TYPE_CHECKING:
    from app.infrastructure.db.models.l2_tools import L2Tool
    from app.layers.l1_raw.models import L1File


class L2Artifact(Base, TimestampMixin):
    """
    L2-B: モダリティから抽出された構造化・中間生成物 (1:N 保持)
    OCR文字認識結果、レイアウト解析結果、テキストチャンク、
    埋め込みベクトル(Vector)等を記録する。
    """

    __tablename__ = "l2_artifacts"

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
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("l2_tools.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="抽出・生成に使用したツールID",
    )
    artifact_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="生成物の種類 (ocr_text, layout_bbox, chunk, embedding など)",
    )
    content_text: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="抽出テキスト本体またはチャンク文字列",
    )
    page_number: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="該当するページ番号 (該当する場合)",
    )
    bounding_box: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="画像・PDF内の座標情報 {x, y, w, h, polygon} など",
    )

    # メタ情報: ベクトルの次元数
    embedding_dim: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="埋め込みベクトルの次元数 (例: 384, 768, 1536)",
    )

    # 32bit float 可変長ベクトル (pgvector)
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(),
        nullable=True,
        comment="標準検索用: 32bit float ベクトル",
    )

    # 16bit halfvec 可変長ベクトル (pgvector 0.7.0+)
    embedding_half: Mapped[Optional[List[float]]] = mapped_column(
        HalfVector(),
        nullable=True,
        comment="実験・比較用: 16bit 半精度 float ベクトル",
    )

    # バイナリ量子化用可変長ビット列 (BIT)
    embedding_bit: Mapped[Optional[str]] = mapped_column(
        BIT(varying=True),
        nullable=True,
        comment="実験・比較用: バイナリベクトル ('101010...' 形式のビット列)",
    )

    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="ツール固有の追加メタデータ (信頼度スコア、フォント情報等)",
    )
    parent_artifact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("l2_artifacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="親となった中間成果物のID (データ血統追跡用)",
    )

    # Relationships
    l1_file: Mapped["L1File"] = relationship(
        "L1File",
        back_populates="l2_artifacts",
    )
    l2_tool: Mapped["L2Tool"] = relationship("L2Tool")

    __table_args__ = (
        Index("idx_l2_artifacts_file_hash_type", "file_hash", "artifact_type"),
    )

