import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, func
from sqlalchemy import Enum as SAEnum, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid_utils import uuid7 as _uuid7

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.users import User


def uuid7() -> uuid.UUID:
    return uuid.UUID(bytes=_uuid7().bytes)


class UserNotificationPreference(Base):
    __tablename__ = "user_notification_preferences"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    email_template_published: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    email_new_signin: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    notify_badge_creation: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="true"
    )
    notify_daily_digest: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="true"
    )
    notify_weekly_report: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="true"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="notification_preferences")


class NotificationType(str, enum.Enum):
    BADGE_CREATION = "badge_creation"
    DAILY_DIGEST = "daily_digest"
    WEEKLY_REPORT = "weekly_report"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid7, index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    type: Mapped[NotificationType] = mapped_column(
        SAEnum(NotificationType, name="notification_type"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(String(2048), nullable=False)
    is_read: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    user: Mapped["User"] = relationship(back_populates="notifications")

    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_user_unread", "user_id", "is_read"),
    )
