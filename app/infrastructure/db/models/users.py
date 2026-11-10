import uuid
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.layers.l1_raw.models import L1FileUpload


class User(Base, TimestampMixin):
    """ユーザーマスタ"""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    username: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="ユーザー名",
    )
    email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,  # メールアドレスなしユーザーやシステムアカウントを許容
        unique=True,
        index=True,
        comment="メールアドレス（任意）",
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="ハッシュ化パスワード",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="有効/無効フラグ",
    )

    # Relationships
    file_uploads: Mapped[List["L1FileUpload"]] = relationship(
        "L1FileUpload",
        back_populates="user",
        cascade="all, delete-orphan",
    )