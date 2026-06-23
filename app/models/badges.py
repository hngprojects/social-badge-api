import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.templates import PlatformTemplate
    from app.models.users import User


class Badge(Base):
    __tablename__ = "badges"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid7, index=True, nullable=False
    )
    organiser_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    platform_template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_templates.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    canvas_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    default_caption: Mapped[str | None] = mapped_column(String(255), nullable=True)
    destination_link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    logo_public_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    access_type: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    access_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    share_slug: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    share_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    creation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationship back to the User
    organiser: Mapped[User] = relationship("User", back_populates="badges")

    # Relationship to PlatformTemplate
    platform_template: Mapped[PlatformTemplate] = relationship(
        "PlatformTemplate",
        back_populates="badges",
    )

    # Relationships to child tables
    hashtags: Mapped[list[BadgeHashtag]] = relationship(
        "BadgeHashtag",
        back_populates="badge",
        cascade="all, delete-orphan",
    )


class BadgeHashtag(Base):
    __tablename__ = "badge_hashtags"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid7, index=True, nullable=False
    )
    badge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("badges.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    hashtag: Mapped[str] = mapped_column(String(255), index=True, nullable=False)

    # Relationship back to the Badge
    badge: Mapped[Badge] = relationship("Badge", back_populates="hashtags")
