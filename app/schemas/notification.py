from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.notifications import NotificationType


class NotificationPreferencesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email_template_published: bool
    email_new_signin: bool
    notify_badge_creation: bool
    notify_daily_digest: bool
    notify_weekly_report: bool
    updated_at: datetime | None = None


class UpdateNotificationPreferencesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email_template_published: bool | None = None
    email_new_signin: bool | None = None
    notify_badge_creation: bool | None = None
    notify_daily_digest: bool | None = None
    notify_weekly_report: bool | None = None


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: NotificationType
    title: str
    body: str
    is_read: bool
    extra_data: dict[str, Any] | None = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    total: int
    page: int
    limit: int
    prev: str | None = None
    next: str | None = None


class UnreadCountResponse(BaseModel):
    unread_count: int = Field(..., description="Number of unread notifications.")


class MarkAllReadResponse(BaseModel):
    marked: int = Field(..., description="Number of notifications marked as read.")
