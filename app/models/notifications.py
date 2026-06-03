import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, func
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

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="notification_preferences")
