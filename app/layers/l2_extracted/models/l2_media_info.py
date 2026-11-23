
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base, TimestampMixin


if TYPE_CHECKING:
    from app.layers.l1_raw.models import L1File


class L2MediaInfo(Base, TimestampMixin):
    """
    L2-A: モダリティ共通・物理属性および抽出メタデータ
    (ファイルハッシュ単位 1:1)。

    Detectorが実データから判定したMIMEタイプと、
    MediaInfo Pluginが抽出した詳細情報を保持する。
    """

    __tablename__ = "l2_media_info"

    file_hash: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("l1_files.file_hash", ondelete="CASCADE"),
        primary_key=True,
        comment="対象ファイルのSHA-256ハッシュ",
    )

    # Detectorによる形式識別結果
    mime_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Detectorが実データから判定したMIMEタイプ",
    )

    # 共通時系列・作成属性
    content_created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="コンテンツの作成/撮影日時",
    )
    author_or_device: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="作成者名または撮影機器/カメラモデル",
    )

    # 画像・動画の物理属性
    width: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="横幅ピクセル",
    )
    height: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="縦幅ピクセル",
    )

    # 位置情報属性
    latitude: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        index=True,
        comment="緯度 (GPS)",
    )
    longitude: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        index=True,
        comment="経度 (GPS)",
    )

    # 音声・動画属性
    duration_seconds: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="再生時間(秒)",
    )
    sample_rate_hz: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="サンプリング周波数(Hz)",
    )
    frame_rate: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="フレームレート(fps)",
    )

    # ドキュメント・テキスト属性
    page_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="PDF・プレゼン等の総ページ数",
    )
    line_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="テキスト・CSV等の総行数",
    )
    encoding: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="テキストファイルの文字コード",
    )

    # Rawメタデータ
    raw_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="抽出ツールが取得した未加工メタデータ全量",
    )

    # Relationship
    l1_file: Mapped["L1File"] = relationship(
        "L1File",
        back_populates="media_info",
    )

