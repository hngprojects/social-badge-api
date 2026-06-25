from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, NotificationType, UserNotificationPreference
from app.schemas.notification import (
    NotificationPreferencesResponse,
)

_DEFAULTS: dict[str, bool] = {
    "email_template_published": True,
    "email_new_signin": True,
    "notify_badge_creation": True,
    "notify_daily_digest": True,
    "notify_weekly_report": True,
}


async def get_notification_preferences(
    session: AsyncSession,
    user_id: UUID,
) -> NotificationPreferencesResponse:
    """
    Retrieves the notification preferences for a specific user.

    Queries the UserNotificationPreference table. If no preferences record exists,
    returns a schema populated with default toggle values.
    """
    result = await session.execute(
        select(UserNotificationPreference).where(
            UserNotificationPreference.user_id == user_id
        )
    )

    prefs = result.scalar_one_or_none()

    if prefs is None:
        return NotificationPreferencesResponse(
            email_template_published=_DEFAULTS["email_template_published"],
            email_new_signin=_DEFAULTS["email_new_signin"],
            notify_badge_creation=_DEFAULTS["notify_badge_creation"],
            notify_daily_digest=_DEFAULTS["notify_daily_digest"],
            notify_weekly_report=_DEFAULTS["notify_weekly_report"],
        )

    return NotificationPreferencesResponse.model_validate(prefs)


async def update_notification_preferences(
    session: AsyncSession,
    user_id: UUID,
    updates: dict[str, bool],
) -> NotificationPreferencesResponse:
    """
    Updates or inserts notification preferences for a user.

    Performs an upsert (INSERT ... ON CONFLICT DO UPDATE) operation
    using PostgreSQL dialect extensions to guarantee that the record is either updated
    or initialized with defaults.
    Commits the transaction and returns the refreshed preferences.
    """
    insert_values: dict[str, object] = {
        "user_id": user_id,
        **{key: _DEFAULTS[key] for key in _DEFAULTS if key not in updates},
        **updates,
    }

    conflict_updates: dict[str, object] = {
        **updates,
        "updated_at": func.now(),
    }

    stmt = (
        pg_insert(UserNotificationPreference)
        .values(**insert_values)
        .on_conflict_do_update(
            index_elements=["user_id"],
            set_=conflict_updates,
        )
    )

    await session.execute(stmt)
    await session.commit()

    result = await session.execute(
        select(UserNotificationPreference).where(
            UserNotificationPreference.user_id == user_id
        )
    )
    prefs = result.scalar_one()
    return NotificationPreferencesResponse.model_validate(prefs)


_TYPE_TO_PREF_FIELD: dict[NotificationType, str] = {
    NotificationType.BADGE_CREATION: "notify_badge_creation",
    NotificationType.DAILY_DIGEST: "notify_daily_digest",
    NotificationType.WEEKLY_REPORT: "notify_weekly_report",
}


async def create_notification(
    session: AsyncSession,
    user_id: UUID,
    notif_type: NotificationType,
    title: str,
    body: str,
    extra_data: dict | None = None,
) -> Notification | None:
    """
    Creates a new in-app notification if the user has enabled alerts
    for that notification type.

    Retrieves the user's preferences, checks the toggle
    corresponding to the notification type, inserts the Notification record if active,
    and flushes the database session to assign an ID.
    Returns the created Notification instance,
    or None if the notification type is disabled.
    """
    result = await session.execute(
        select(UserNotificationPreference).where(
            UserNotificationPreference.user_id == user_id
        )
    )
    prefs = result.scalar_one_or_none()

    pref_field = _TYPE_TO_PREF_FIELD[notif_type]
    if prefs is not None and not getattr(prefs, pref_field):
        return None

    notification = Notification(
        user_id=user_id,
        type=notif_type,
        title=title,
        body=body,
        extra_data=extra_data,
    )
    session.add(notification)
    await session.flush()
    return notification


async def list_notifications(
    session: AsyncSession,
    user_id: UUID,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[Notification], int]:
    """
    Retrieves a paginated list of all notifications for a user, sorted newest first.

    Queries both the total count of notifications for the user and the slice
    matching the limit and page offset.
    """
    where_clause = Notification.user_id == user_id

    count_result = await session.execute(
        select(func.count(Notification.id)).where(where_clause)
    )
    total = count_result.scalar_one()

    result = await session.execute(
        select(Notification)
        .where(where_clause)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    notifications = list(result.scalars().all())
    return notifications, total


async def get_unread_count(session: AsyncSession, user_id: UUID) -> int:
    """Returns the total number of unread notifications for a user."""
    result = await session.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
        )
    )
    return int(result.scalar_one())


async def mark_notification_read(
    session: AsyncSession,
    user_id: UUID,
    notification_id: UUID,
) -> bool:
    """
    Marks a single notification as read if it belongs to the specified user.

    Executes an update query, commits the changes, and returns a boolean
    indicating whether a matching notification row was updated.
    """
    result = await session.execute(
        sa_update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
        .values(is_read=True)
    )
    await session.commit()
    return result.rowcount > 0


async def mark_all_notifications_read(
    session: AsyncSession,
    user_id: UUID,
) -> int:
    """
    Marks all unread notifications for a user as read.

    Executes a bulk update query, commits the session,
    and returns the count of updated rows.
    """
    result = await session.execute(
        sa_update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True)
    )
    await session.commit()
    return result.rowcount
