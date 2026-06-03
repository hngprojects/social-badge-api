import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import hash_password
from app.models.users import User
from app.services.notification import (
    get_notification_preferences,
    update_notification_preferences,
)
from tests.conftest import create_db_engine


@pytest.fixture
async def service_user(db_session: AsyncSession) -> User:
    """Create a test user for notification service tests."""
    user = User(
        first_name="Service",
        last_name="User",
        email="service_notifications@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_get_default_preferences(
    db_session: AsyncSession,
    service_user: User,
) -> None:
    """Retrieving preferences when none have been set returns default values."""
    prefs = await get_notification_preferences(db_session, service_user.id)
    assert prefs.email_template_published is True
    assert prefs.email_new_signin is True
    assert prefs.updated_at is None


async def test_update_preferences_new(
    db_session: AsyncSession,
    service_user: User,
) -> None:
    """Updating preferences for the first time persists them
    and defaults missing ones to True."""
    updates = {"email_template_published": False}

    # Verify updates returned and stored
    prefs = await update_notification_preferences(db_session, service_user.id, updates)
    assert prefs.email_template_published is False
    assert prefs.email_new_signin is True  # Defaults to True
    assert prefs.updated_at is not None


async def test_update_preferences_existing_partial(
    db_session: AsyncSession,
    service_user: User,
) -> None:
    """Updating an existing preference partially updates only the specified fields,
    leaving others unchanged."""
    # Create initial preferences (both False)
    await update_notification_preferences(
        db_session,
        service_user.id,
        {"email_template_published": False, "email_new_signin": False},
    )

    # Perform a partial update to enable signin notifications
    prefs = await update_notification_preferences(
        db_session,
        service_user.id,
        {"email_new_signin": True},
    )

    assert prefs.email_template_published is False  # Left unchanged
    assert prefs.email_new_signin is True  # Updated


async def test_concurrent_updates_last_write_wins(
    service_user: User,
) -> None:
    """Concurrent updates from two different sessions succeed without corruption,
    and last write wins."""
    engine = create_db_engine()
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # We will use two separate sessions to simulate concurrent clients/devices
    async with session_factory() as session1, session_factory() as session2:
        # Task 1 wants to set email_template_published=False, email_new_signin=True
        # Task 2 wants to set email_template_published=True, email_new_signin=False

        async def run_update_1():
            return await update_notification_preferences(
                session1,
                service_user.id,
                {"email_template_published": False, "email_new_signin": True},
            )

        async def run_update_2():
            # ensure it executes slightly after or alongside
            await asyncio.sleep(0.01)
            return await update_notification_preferences(
                session2,
                service_user.id,
                {"email_template_published": True, "email_new_signin": False},
            )

        # Run them concurrently
        res1, res2 = await asyncio.gather(run_update_1(), run_update_2())

        # Assert no exceptions were thrown and both returned valid preferences
        assert res1.updated_at is not None
        assert res2.updated_at is not None

        # Verify database has the state of the final commit (last write wins)
        # Using a fresh session to read final state from DB
        async with session_factory() as verify_session:
            final_prefs = await get_notification_preferences(
                verify_session, service_user.id
            )

            assert (
                final_prefs.email_template_published is False
                and final_prefs.email_new_signin is True
            ) or (
                final_prefs.email_template_published is True
                and final_prefs.email_new_signin is False
            )

    await engine.dispose()
