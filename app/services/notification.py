from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserNotificationPreference
from app.schemas.notification import NotificationPreferencesResponse

_DEFAULTS: dict[str, bool] = {
    "email_template_published": True,
    "email_new_signin": True,
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

    stmt = (
        pg_insert(UserNotificationPreference)
        .values(**insert_values)
        .on_conflict_do_update(
            index_elements=["user_id"],
            # Only overwrite the columns the client explicitly sent.
            set_=updates,
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
