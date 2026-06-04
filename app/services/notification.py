from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, NotificationType, UserNotificationPreference
from app.schemas.notification import (
    NotificationListResponse,
    NotificationPreferencesResponse,
    NotificationResponse,
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
    """Persist notification preference changes for an organiser.

    Uses a PostgreSQL upsert so:
    - A first-time write creates the row with defaults for any field not
        included in `updates`.
    - A subsequent write only touches the columns present in `updates`;
        everything else is left at its stored value.
    - Concurrent writes from two devices are handled atomically by the
        database — last write wins with no risk of data corruption.
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
            # Only overwrite the columns the client explicitly sent.
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
    """Create a notification if the user's toggle for this type is on.

    Returns the created notification, or None if the toggle is off.
    Caller is responsible for commit — this function only flushes.
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
    """Return paginated notifications for a user, newest first."""
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
    """Return the count of unread notifications for a user."""
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
    """Mark one notification as read. Returns False if not found or not owned."""
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
    """Mark every unread notification for the user as read. Returns the count."""
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
