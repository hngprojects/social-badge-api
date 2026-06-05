"""Scheduled jobs that generate Daily Digest and Weekly Report notifications.

Both jobs aggregate metrics for each organiser whose toggle for that
notification type is on, then create one in-app notification per organiser.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models import Badge, Notification, NotificationType, UserNotificationPreference
from app.services.notification import create_notification

logger = logging.getLogger(__name__)

_session_factory: async_sessionmaker | None = None


def _get_session_factory() -> async_sessionmaker:
    """Lazily build (and cache) a session factory for the worker process.

    Cached at module level so the engine is created once per worker
    process, not once per cron run.
    """
    global _session_factory
    if _session_factory is None:
        engine = create_async_engine(
            str(settings.DATABASE_URL),
            pool_pre_ping=True,
        )
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


async def send_daily_digests(ctx: dict) -> dict:
    """Send a daily digest notification to each organiser whose toggle is on.

    The digest counts every participant-generated badge across all the
    organiser's published badges for the day, plus the total share count
    increments. Uses the current UTC day.

    Returns a small summary dict for arq's job log.
    """
    session_factory = _get_session_factory()
    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    sent = 0
    skipped = 0

    async with session_factory() as session:
        prefs_result = await session.execute(
            select(UserNotificationPreference.user_id).where(
                UserNotificationPreference.notify_daily_digest.is_(True)
            )
        )
        opted_in_user_ids = {row[0] for row in prefs_result.all()}

        all_owners_result = await session.execute(select(Badge.organiser_id).distinct())
        all_owner_ids = {row[0] for row in all_owners_result.all()}

        users_with_prefs_result = await session.execute(
            select(UserNotificationPreference.user_id)
        )
        users_with_prefs = {row[0] for row in users_with_prefs_result.all()}
        defaulted_in = all_owner_ids - users_with_prefs
        target_users = opted_in_user_ids | defaulted_in

        counts_result = await session.execute(
            select(
                Notification.user_id,
                func.count(Notification.id).label("count"),
            )
            .where(
                Notification.type == NotificationType.BADGE_CREATION,
                Notification.created_at >= day_start,
                Notification.created_at < day_end,
                Notification.user_id.in_(target_users),
            )
            .group_by(Notification.user_id)
        )
        counts_by_user = {row[0]: int(row[1]) for row in counts_result.all()}

        for user_id in target_users:
            badges_created_today = counts_by_user.get(user_id, 0)

            if badges_created_today == 0:
                skipped += 1
                continue

            title = "Daily digest"
            body = (
                f"Today's recap: {badges_created_today} new badge"
                f"{'s' if badges_created_today != 1 else ''} created from your "
                f"badges."
            )

            notif = await create_notification(
                session=session,
                user_id=user_id,
                notif_type=NotificationType.DAILY_DIGEST,
                title=title,
                body=body,
                extra_data={
                    "badges_created": badges_created_today,
                    "period_start": day_start.isoformat(),
                    "period_end": day_end.isoformat(),
                },
            )
            if notif is not None:
                await session.commit()
                sent += 1
            else:
                skipped += 1

    logger.info(
        "daily_digest finished: sent=%d skipped=%d total_targets=%d",
        sent,
        skipped,
        len(target_users),
    )
    return {"sent": sent, "skipped": skipped, "total_targets": len(target_users)}


async def send_weekly_reports(ctx: dict) -> dict:
    """Send a weekly report notification to each organiser whose toggle is on.

    The report covers the last 7 days. Includes total badges created and
    the day of the week with the highest activity.
    """
    session_factory = _get_session_factory()
    now = datetime.now(UTC)
    week_end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
        days=1
    )
    week_start = week_end - timedelta(days=7)

    weekday_names = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    sent = 0
    skipped = 0

    async with session_factory() as session:
        prefs_result = await session.execute(
            select(UserNotificationPreference.user_id).where(
                UserNotificationPreference.notify_weekly_report.is_(True)
            )
        )
        opted_in_user_ids = {row[0] for row in prefs_result.all()}

        all_owners_result = await session.execute(select(Badge.organiser_id).distinct())
        all_owner_ids = {row[0] for row in all_owners_result.all()}

        users_with_prefs_result = await session.execute(
            select(UserNotificationPreference.user_id)
        )
        users_with_prefs = {row[0] for row in users_with_prefs_result.all()}

        defaulted_in = all_owner_ids - users_with_prefs
        target_users = opted_in_user_ids | defaulted_in

        counts_result = await session.execute(
            select(
                Notification.user_id,
                func.count(Notification.id).label("count"),
            )
            .where(
                Notification.type == NotificationType.BADGE_CREATION,
                Notification.created_at >= week_start,
                Notification.created_at < week_end,
                Notification.user_id.in_(target_users),
            )
            .group_by(Notification.user_id)
        )
        counts_by_user = {row[0]: int(row[1]) for row in counts_result.all()}

        for user_id in target_users:
            week_total = counts_by_user.get(user_id, 0)

            if week_total == 0:
                skipped += 1
                continue

            per_day_result = await session.execute(
                select(
                    func.extract("dow", Notification.created_at).label("dow"),
                    func.count(Notification.id).label("count"),
                )
                .where(
                    Notification.user_id == user_id,
                    Notification.type == NotificationType.BADGE_CREATION,
                    Notification.created_at >= week_start,
                    Notification.created_at < week_end,
                )
                .group_by("dow")
                .order_by(func.count(Notification.id).desc(), "dow")
            )
            per_day = per_day_result.all()
            top_dow = int(per_day[0][0])
            top_day_name = weekday_names[(top_dow - 1) % 7]

            title = "Weekly report"
            body = (
                f"This week: {week_total} new badge"
                f"{'s' if week_total != 1 else ''} created. "
                f"Highest-traffic day: {top_day_name}."
            )

            notif = await create_notification(
                session=session,
                user_id=user_id,
                notif_type=NotificationType.WEEKLY_REPORT,
                title=title,
                body=body,
                extra_data={
                    "week_total": week_total,
                    "top_day": top_day_name,
                    "per_day_counts": [
                        {"dow": int(row[0]), "count": int(row[1])} for row in per_day
                    ],
                    "period_start": week_start.isoformat(),
                    "period_end": week_end.isoformat(),
                },
            )
            if notif is not None:
                await session.commit()
                sent += 1
            else:
                skipped += 1

    logger.info(
        "weekly_report finished: sent=%d skipped=%d total_targets=%d",
        sent,
        skipped,
        len(target_users),
    )
    return {"sent": sent, "skipped": skipped, "total_targets": len(target_users)}
