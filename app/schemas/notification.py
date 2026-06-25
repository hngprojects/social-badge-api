from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.notifications import NotificationType


class NotificationPreferencesResponse(BaseModel):
    """
    Data transfer object representing a user's notification settings and preferences,
    defining toggle states for email alerts and digests.
    """

    model_config = ConfigDict(from_attributes=True)

    email_template_published: bool
    email_new_signin: bool
    notify_badge_creation: bool
    notify_daily_digest: bool
    notify_weekly_report: bool
    updated_at: datetime | None = None


class UpdateNotificationPreferencesRequest(BaseModel):
    """
    Data transfer object representing a request to update user notification preferences,
    allowing partial updates to settings while ignoring extra fields.
    """

    model_config = ConfigDict(extra="ignore")

    email_template_published: bool | None = None
    email_new_signin: bool | None = None
    notify_badge_creation: bool | None = None
    notify_daily_digest: bool | None = None
    notify_weekly_report: bool | None = None


class NotificationResponse(BaseModel):
    """
    Data transfer object representing details of a single user notification,
    including the type, status, subject text, and optional payload.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: NotificationType
    title: str
    body: str
    is_read: bool
    extra_data: dict[str, Any] | None = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    """
    Data transfer object representing a paginated list of notifications,
    containing the matching notifications and pagination navigation links.
    """

    notifications: list[NotificationResponse]
    total: int
    page: int
    limit: int
    prev: str | None = None
    next: str | None = None


class UnreadCountResponse(BaseModel):
    """
    Data transfer object representing the total count of unread notifications
    for the authenticated user.
    """

    unread_count: int = Field(..., description="Number of unread notifications.")


class MarkAllReadResponse(BaseModel):
    """
    Data transfer object indicating the result of marking all notifications as read,
    returning the count of updated records.
    """

    marked: int = Field(..., description="Number of notifications marked as read.")
