import uuid
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.infrastructure.db.models.users import User
    from app.layers.l1_raw.models import L1FileUpload


class Group(Base, TimestampMixin):
    """
    家族・チーム等のグループ管理テーブル (Auth層)
    """

    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="グループ名 (例: 山田家, 開発チーム)",
    )
    description: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="グループの概要説明",
    )

    # Relationships
    members: Mapped[List["GroupMember"]] = relationship(
        "GroupMember",
        back_populates="group",
        cascade="all, delete-orphan",
    )


class GroupMember(Base, TimestampMixin):
    """
    グループ所属メンバーと役割 (Auth層)
    """

    __tablename__ = "group_members"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(
        String(50),
        default="Member",
        nullable=False,
        comment="グループ内役割 (Owner / Admin / Member)",
    )

    # Relationships
    group: Mapped["Group"] = relationship("Group", back_populates="members")
    user: Mapped["User"] = relationship("User")


class ResourceShare(Base, TimestampMixin):
    """
    共有スコープと操作権限エントリー (ACL層)
    """

    __tablename__ = "resource_shares"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    file_upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("l1_file_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="共有対象のファイルアップロードID",
    )
    grantee_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="共有先種別 (group / user)",
    )
    grantee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="共有先グループID または ユーザーID",
    )
    permission_level: Mapped[str] = mapped_column(
        String(20),
        default="Read",
        nullable=False,
        comment="権限レベル (Admin / Write / Read)",
    )

    # Relationships
    file_upload: Mapped["L1FileUpload"] = relationship(
        "L1FileUpload",
        back_populates="shares",
    )

    __table_args__ = (
        UniqueConstraint("file_upload_id", "grantee_type", "grantee_id", name="uq_resource_share_grantee"),
    )
