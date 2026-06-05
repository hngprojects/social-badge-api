"""Tests for the daily digest and weekly report scheduled jobs.

These call the job coroutines directly rather than running arq, so the
cron scheduling itself isn't exercised. The cron config is verified
separately by importing WorkerSettings.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import (
    Badge,
    Notification,
    NotificationType,
    PlatformTemplate,
    UserNotificationPreference,
)
from app.models.users import User
from app.workers import digest_jobs


@pytest.fixture
async def organiser(db_session: AsyncSession) -> User:
    user = User(
        first_name="Digest",
        last_name="Organiser",
        email="digest_org@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def platform_template(db_session: AsyncSession) -> PlatformTemplate:
    tpl = PlatformTemplate(
        title="Test Template",
        category="festivals",
        canvas_data={"layout_id": "v1"},
        is_active=True,
    )
    db_session.add(tpl)
    await db_session.commit()
    await db_session.refresh(tpl)
    return tpl


@pytest.fixture
async def badge(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> Badge:
    b = Badge(
        organiser_id=organiser.id,
        platform_template_id=platform_template.id,
        title="Test Badge",
        canvas_data={"layout": "v1"},
        is_published=True,
        share_slug="digest-test-slug",
    )
    db_session.add(b)
    await db_session.commit()
    await db_session.refresh(b)
    return b


async def _create_badge_creation_notif(
    db_session: AsyncSession,
    user_id,
    created_at: datetime,
    badge_id=None,
) -> Notification:
    """Insert a BADGE_CREATION notification with a specific timestamp."""
    n = Notification(
        user_id=user_id,
        type=NotificationType.BADGE_CREATION,
        title="A badge was created",
        body="x",
        extra_data={"badge_id": str(badge_id)} if badge_id else None,
    )
    db_session.add(n)
    await db_session.flush()
    n.created_at = created_at
    await db_session.commit()
    return n


def _patch_session_factory(db_session: AsyncSession):
    """Patch _get_session_factory so the worker reuses the test session.

    Returns a context manager that yields the session each time the
    worker asks for one.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_session():
        yield db_session

    class FakeFactory:
        def __call__(self):
            return fake_session()

    return patch.object(digest_jobs, "_get_session_factory", lambda: FakeFactory())


async def test_daily_digest_sends_when_activity_today(
    db_session: AsyncSession,
    organiser: User,
    badge: Badge,
) -> None:
    """A digest is sent when the organiser has badge_creation rows for today."""
    today_morning = datetime.now(UTC).replace(hour=8, minute=0, second=0, microsecond=0)
    for _ in range(3):
        await _create_badge_creation_notif(
            db_session, organiser.id, today_morning, badge.id
        )

    with _patch_session_factory(db_session):
        result = await digest_jobs.send_daily_digests({})

    assert result["sent"] == 1
    assert result["skipped"] == 0

    digests = await db_session.execute(
        select(Notification).where(
            Notification.user_id == organiser.id,
            Notification.type == NotificationType.DAILY_DIGEST,
        )
    )
    digest = digests.scalar_one()
    assert "3 new badges" in digest.body
    assert digest.extra_data is not None
    assert digest.extra_data["badges_created"] == 3


async def test_daily_digest_singular_phrasing(
    db_session: AsyncSession,
    organiser: User,
    badge: Badge,
) -> None:
    """Body uses 'badge' (singular) when count is 1."""
    today = datetime.now(UTC).replace(hour=8, minute=0, second=0, microsecond=0)
    await _create_badge_creation_notif(db_session, organiser.id, today, badge.id)

    with _patch_session_factory(db_session):
        await digest_jobs.send_daily_digests({})

    digests = await db_session.execute(
        select(Notification).where(
            Notification.user_id == organiser.id,
            Notification.type == NotificationType.DAILY_DIGEST,
        )
    )
    digest = digests.scalar_one()
    assert "1 new badge created" in digest.body


async def test_daily_digest_skips_when_no_activity(
    db_session: AsyncSession,
    organiser: User,
    badge: Badge,
) -> None:
    """No digest is sent when the organiser had zero badge_creation rows today."""
    five_days_ago = datetime.now(UTC) - timedelta(days=5)
    await _create_badge_creation_notif(
        db_session, organiser.id, five_days_ago, badge.id
    )

    with _patch_session_factory(db_session):
        result = await digest_jobs.send_daily_digests({})

    assert result["sent"] == 0
    assert result["skipped"] == 1

    digests = await db_session.execute(
        select(Notification).where(
            Notification.user_id == organiser.id,
            Notification.type == NotificationType.DAILY_DIGEST,
        )
    )
    assert digests.scalar_one_or_none() is None


async def test_daily_digest_respects_toggle_off(
    db_session: AsyncSession,
    organiser: User,
    badge: Badge,
) -> None:
    """An organiser with notify_daily_digest=False gets no digest, even with activity."""
    today = datetime.now(UTC).replace(hour=8, minute=0, second=0, microsecond=0)
    for _ in range(2):
        await _create_badge_creation_notif(db_session, organiser.id, today, badge.id)

    prefs = UserNotificationPreference(
        user_id=organiser.id,
        email_template_published=True,
        email_new_signin=True,
        notify_badge_creation=True,
        notify_daily_digest=False,
        notify_weekly_report=True,
    )
    db_session.add(prefs)
    await db_session.commit()

    with _patch_session_factory(db_session):
        result = await digest_jobs.send_daily_digests({})

    assert result["sent"] == 0

    digests = await db_session.execute(
        select(Notification).where(
            Notification.user_id == organiser.id,
            Notification.type == NotificationType.DAILY_DIGEST,
        )
    )
    assert digests.scalar_one_or_none() is None


async def test_daily_digest_only_counts_today(
    db_session: AsyncSession,
    organiser: User,
    badge: Badge,
) -> None:
    """Notifications from yesterday don't contribute to today's digest."""
    yesterday = datetime.now(UTC) - timedelta(days=1)
    today = datetime.now(UTC).replace(hour=8, minute=0, second=0, microsecond=0)

    await _create_badge_creation_notif(db_session, organiser.id, yesterday, badge.id)
    await _create_badge_creation_notif(db_session, organiser.id, today, badge.id)
    await _create_badge_creation_notif(db_session, organiser.id, today, badge.id)

    with _patch_session_factory(db_session):
        await digest_jobs.send_daily_digests({})

    digests = await db_session.execute(
        select(Notification).where(
            Notification.user_id == organiser.id,
            Notification.type == NotificationType.DAILY_DIGEST,
        )
    )
    digest = digests.scalar_one()
    assert digest.extra_data is not None
    assert digest.extra_data["badges_created"] == 2


async def test_weekly_report_sends_with_top_day(
    db_session: AsyncSession,
    organiser: User,
    badge: Badge,
) -> None:
    """Weekly report aggregates 7 days and identifies the highest-traffic day."""
    now = datetime.now(UTC)

    three_days_ago = now - timedelta(days=3)
    for _ in range(5):
        await _create_badge_creation_notif(
            db_session, organiser.id, three_days_ago, badge.id
        )

    one_day_ago = now - timedelta(days=1)
    for _ in range(2):
        await _create_badge_creation_notif(
            db_session, organiser.id, one_day_ago, badge.id
        )

    with _patch_session_factory(db_session):
        result = await digest_jobs.send_weekly_reports({})

    assert result["sent"] == 1

    reports = await db_session.execute(
        select(Notification).where(
            Notification.user_id == organiser.id,
            Notification.type == NotificationType.WEEKLY_REPORT,
        )
    )
    report = reports.scalar_one()
    assert report.extra_data is not None
    assert report.extra_data["week_total"] == 7
    assert "7 new badges" in report.body
    expected_weekday_names = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    expected_top = expected_weekday_names[three_days_ago.weekday()]
    assert report.extra_data["top_day"] == expected_top


async def test_weekly_report_skips_when_no_activity(
    db_session: AsyncSession,
    organiser: User,
    badge: Badge,
) -> None:
    """No report is sent when the organiser had zero badge_creation rows this week."""
    ten_days_ago = datetime.now(UTC) - timedelta(days=10)
    await _create_badge_creation_notif(db_session, organiser.id, ten_days_ago, badge.id)

    with _patch_session_factory(db_session):
        result = await digest_jobs.send_weekly_reports({})

    assert result["sent"] == 0
    assert result["skipped"] == 1


async def test_weekly_report_respects_toggle_off(
    db_session: AsyncSession,
    organiser: User,
    badge: Badge,
) -> None:
    """An organiser with notify_weekly_report=False gets no report."""
    today = datetime.now(UTC).replace(hour=8, minute=0, second=0, microsecond=0)
    await _create_badge_creation_notif(db_session, organiser.id, today, badge.id)

    prefs = UserNotificationPreference(
        user_id=organiser.id,
        email_template_published=True,
        email_new_signin=True,
        notify_badge_creation=True,
        notify_daily_digest=True,
        notify_weekly_report=False,
    )
    db_session.add(prefs)
    await db_session.commit()

    with _patch_session_factory(db_session):
        result = await digest_jobs.send_weekly_reports({})

    assert result["sent"] == 0

    reports = await db_session.execute(
        select(Notification).where(
            Notification.user_id == organiser.id,
            Notification.type == NotificationType.WEEKLY_REPORT,
        )
    )
    assert reports.scalar_one_or_none() is None


async def test_daily_digest_scopes_to_each_organiser(
    db_session: AsyncSession,
    organiser: User,
    badge: Badge,
    platform_template: PlatformTemplate,
) -> None:
    """Two organisers each get their own digest with their own counts."""
    other_user = User(
        first_name="Other",
        last_name="Org",
        email="other_org@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)

    other_badge = Badge(
        organiser_id=other_user.id,
        platform_template_id=platform_template.id,
        title="Other Badge",
        canvas_data={"layout": "v1"},
        is_published=True,
        share_slug="other-slug",
    )
    db_session.add(other_badge)
    await db_session.commit()
    await db_session.refresh(other_badge)

    today = datetime.now(UTC).replace(hour=8, minute=0, second=0, microsecond=0)
    for _ in range(2):
        await _create_badge_creation_notif(db_session, organiser.id, today, badge.id)
    for _ in range(4):
        await _create_badge_creation_notif(
            db_session, other_user.id, today, other_badge.id
        )

    with _patch_session_factory(db_session):
        result = await digest_jobs.send_daily_digests({})

    assert result["sent"] == 2

    primary_digest = (
        await db_session.execute(
            select(Notification).where(
                Notification.user_id == organiser.id,
                Notification.type == NotificationType.DAILY_DIGEST,
            )
        )
    ).scalar_one()
    other_digest = (
        await db_session.execute(
            select(Notification).where(
                Notification.user_id == other_user.id,
                Notification.type == NotificationType.DAILY_DIGEST,
            )
        )
    ).scalar_one()

    assert primary_digest.extra_data is not None
    assert primary_digest.extra_data["badges_created"] == 2
    assert other_digest.extra_data is not None
    assert other_digest.extra_data["badges_created"] == 4
