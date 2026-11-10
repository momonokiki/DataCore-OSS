import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional
from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID, BIT
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType  # ★ 追加

from app.infrastructure.db.base import Base, TimestampMixin

# ★ pgvector の halfvec (16-bit float) 用カスタム型を自前で定義
class HalfVector(UserDefinedType):
    """SQLAlchemy custom type for pgvector halfvec (16-bit float vector)"""
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


class L2MediaInfo(Base, TimestampMixin):
    """
    L2-A: モダリティ共通・物理属性および抽出メタデータ (ファイルハッシュ単位 1:1)
    画像(EXIF)、PDF(Document Info)、Office、テキスト/CSV等のファイルメタデータを抽象化して統合保持します。
    """

    __tablename__ = "l2_media_info"

    file_hash: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("l1_files.file_hash", ondelete="CASCADE"),
        primary_key=True,
        comment="対象ファイルのSHA-256ハッシュ",
    )

    # 1. 共通時系列・作成属性 (Exif撮影日時 / PDF作成日時 / 文書作成日時)
    content_created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="コンテンツの作成/撮影日時 (EXIF DateTimeOriginal / PDF CreationDate)",
    )
    author_or_device: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="作成者名 または 撮影機器/カメラモデル (EXIF Make+Model / PDF Author)",
    )

    # 2. 画像・動画の物理属性
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="横幅ピクセル")
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="縦幅ピクセル")

    # 3. 位置情報属性 (画像・写真用)
    latitude: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, index=True, comment="EXIF: 緯度 (GPS)"
    )
    longitude: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, index=True, comment="EXIF: 経度 (GPS)"
    )

    # 4. 音声・動画属性
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="再生時間(秒)")
    sample_rate_hz: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="サンプリング周波数(Hz)")
    frame_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="フレームレート(fps)")

    # 5. ドキュメント・テキスト属性
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="PDF・プレゼン等の総ページ数")
    line_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="テキスト・CSV等の総行数")
    encoding: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="テキストファイルの文字コード (UTF-8, Shift_JIS等)")

    # 6. Rawメタデータ (元データロスレス保存)
    raw_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="抽出ツールが取得した未加工メタデータ全量 (EXIF全タグ, PDF Info Dictionary等)",
    )

    # Relationship
    l1_file: Mapped["L1File"] = relationship("L1File", back_populates="media_info")


class L2Artifact(Base, TimestampMixin):
    """
    L2-B: モダリティから抽出された構造化・中間生成物 (1:N 保持)
    OCR文字認識結果、レイアウト解析結果、テキストチャンク、埋め込みベクトル(Vector)等を記録します。
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

    # 1. 標準: 32bit float 可変長ベクトル (pgvector)
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(),
        nullable=True,
        comment="標準検索用: 32bit float ベクトル",
    )

    # 2. 実験用: 16bit halfvec 可変長ベクトル (pgvector 0.7.0+)
    embedding_half: Mapped[Optional[List[float]]] = mapped_column(
        HalfVector(),
        nullable=True,
        comment="実験・比較用: 16bit 半精度 float ベクトル",
    )

    # 3. 実験用: バイナリ量子化用可変長ビット列 (BIT)
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
        ForeignKey("l2_artifacts.id", ondelete="SET NULL"),  # 💡 親が消えても子は生き残る！
        nullable=True, 
        index=True,
        comment="親となった中間成果物のID (データ血統追跡用)"
    )

    # Relationships
    l1_file: Mapped["L1File"] = relationship("L1File", back_populates="l2_artifacts")
    l2_tool: Mapped["L2Tool"] = relationship("L2Tool")

    __table_args__ = (
        Index("idx_l2_artifacts_file_hash_type", "file_hash", "artifact_type"),
    )
