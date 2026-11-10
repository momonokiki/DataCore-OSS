import uuid
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.infrastructure.db.models.users import User
    from app.layers.l2_extracted.models import L2Artifact, L2MediaInfo
#    from app.layers.l3_structured.models import L3DocumentBase


class L1File(Base, TimestampMixin):
    """L1-A: CAS (Content Addressable Storage) 物理ファイル実体 (ハッシュ単位でユニーク)"""

    __tablename__ = "l1_files"

    file_hash: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        comment="SHA-256 ハッシュ値 (CASの主キー)",
    )
    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="MIMEタイプ",
    )
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="ファイルサイズ (バイト)",
    )
    storage_path: Mapped[str] = mapped_column(
        String(512),
        nullable=True,
        comment="CASストレージ内の相対保存パス",
    )

    # Relationships
    uploads: Mapped[List["L1FileUpload"]] = relationship(
        "L1FileUpload",
        back_populates="l1_file",
        cascade="all, delete-orphan",
    )
    media_info: Mapped[Optional["L2MediaInfo"]] = relationship(
        "L2MediaInfo",
        back_populates="l1_file",
        uselist=False,
        cascade="all, delete-orphan",
    )
    l2_artifacts: Mapped[List["L2Artifact"]] = relationship(
        "L2Artifact",
        back_populates="l1_file",
        cascade="all, delete-orphan",
    )


class L1FileUpload(Base, TimestampMixin):
    """L1-B: アップロード履歴・所有権・論理ファイルメタデータ"""

    __tablename__ = "l1_file_uploads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所有ユーザーのID",
    )
    file_hash: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("l1_files.file_hash", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="対象の物理ファイルハッシュ",
    )
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="アップロード時の元ファイル名",
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="file_uploads")
    l1_file: Mapped["L1File"] = relationship("L1File", back_populates="uploads")

    shares: Mapped[List["ResourceShare"]] = relationship(
        "ResourceShare",
        back_populates="file_upload",
        cascade="all, delete-orphan",
    )
