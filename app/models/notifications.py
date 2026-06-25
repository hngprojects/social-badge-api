import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.users import User


class UserNotificationPreference(Base):
    """Database representation of user-specific notification preferences.

    Configures opt-in/opt-out toggles for various email alerts, daily digests, and
    weekly reporting.
    """

    __tablename__ = "user_notification_preferences"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
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

    user: Mapped[User] = relationship(back_populates="notification_preferences")


class NotificationType(enum.StrEnum):
    """Enumeration of supported notification types within the system.

    Defines categories such as badge creation alerts, daily digests, and weekly reports.
    """

    BADGE_CREATION = "badge_alert"
    DAILY_DIGEST = "daily_digest"
    WEEKLY_REPORT = "weekly_report"


class Notification(Base):
    """Database representation of an individual user notification.

    Stores the notification type, message title, body text, read/unread status, and
    optional contextual metadata (extra data) for system alerts and communications.
    """

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid7, nullable=False
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
        Boolean, default=False, nullable=False, index=True, server_default="false"
    )
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    user: Mapped[User] = relationship(back_populates="notifications")

    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_user_unread", "user_id", "is_read"),
    )
