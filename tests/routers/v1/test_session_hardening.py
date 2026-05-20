"""RFC-001 session hardening tests."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.core.token import hash_token
from app.models.auth import RefreshToken
from app.models.users import User

ASYNC_SLEEP_SECONDS = 0.1


async def _create_verified_user(
    session: AsyncSession, email: str = "session@example.com"
) -> User:
    """Create and return a verified user for session tests."""
    user = User(
        first_name="Session",
        last_name="User",
        email=email,
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _login_user(
    client: AsyncClient, email: str, password: str
) -> tuple[str, str]:
    """Log in and return access and refresh token cookies."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    access = response.cookies.get(settings.ACCESS_COOKIE)
    refresh = response.cookies.get(settings.REFRESH_COOKIE)
    assert access is not None
    assert refresh is not None
    return access, refresh


async def _get_family_id_for_raw_token(session: AsyncSession, raw_token: str) -> str:
    """Return the family_id for a given raw refresh token."""
    token_hash = hash_token(raw_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    row = result.scalars().first()
    assert row is not None
    return str(row.family_id)


async def test_rotation_sets_same_family_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _create_verified_user(db_session)
    _, refresh = await _login_user(client, user.email, "StrongPassword1!")

    family_before = await _get_family_id_for_raw_token(db_session, refresh)

    response = await client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE: refresh},
    )
    assert response.status_code == 200

    new_refresh = response.cookies.get(settings.REFRESH_COOKIE)
    assert new_refresh is not None

    family_after = await _get_family_id_for_raw_token(db_session, new_refresh)
    assert family_before == family_after


async def test_reuse_of_revoked_token_revokes_family(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _create_verified_user(db_session, "reuse@example.com")
    _, original_refresh = await _login_user(client, user.email, "StrongPassword1!")

    rotate_response = await client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE: original_refresh},
    )
    assert rotate_response.status_code == 200
    new_refresh = rotate_response.cookies.get(settings.REFRESH_COOKIE)
    assert new_refresh is not None

    # Outside grace window so reuse triggers family revocation,
    # not duplicate-request handling.
    token_hash = hash_token(original_refresh)
    result = await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    token_obj = result.scalars().first()
    assert token_obj is not None
    token_obj.last_used_at = datetime.now(UTC) - timedelta(
        seconds=settings.REFRESH_REUSE_GRACE_SECONDS + 10
    )
    await db_session.commit()

    reuse_response = await client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE: original_refresh},
    )
    assert reuse_response.status_code == 401

    follow_up = await client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE: new_refresh},
    )
    assert follow_up.status_code == 401


async def test_concurrent_refresh_grace_window_not_treated_as_reuse(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _create_verified_user(db_session, "grace@example.com")
    _, original_refresh = await _login_user(client, user.email, "StrongPassword1!")

    rotate_response = await client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE: original_refresh},
    )
    assert rotate_response.status_code == 200
    new_refresh = rotate_response.cookies.get(settings.REFRESH_COOKIE)
    assert new_refresh is not None

    reuse_response = await client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE: original_refresh},
    )
    assert reuse_response.status_code == 401

    follow_up = await client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE: new_refresh},
    )
    assert follow_up.status_code == 200


async def test_expired_token_raises_invalid_refresh_token_error(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _create_verified_user(db_session, "expired@example.com")
    _, refresh = await _login_user(client, user.email, "StrongPassword1!")

    token_hash = hash_token(refresh)
    result = await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    token_obj = result.scalars().first()
    assert token_obj is not None
    token_obj.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE: refresh},
    )
    assert response.status_code == 401


async def test_logout_all_revokes_all_user_sessions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _create_verified_user(db_session, "logoutall@example.com")
    access_1, refresh_1 = await _login_user(client, user.email, "StrongPassword1!")
    _, refresh_2 = await _login_user(client, user.email, "StrongPassword1!")

    response = await client.post(
        "/api/v1/auth/logout/all",
        cookies={
            settings.ACCESS_COOKIE: access_1,
            settings.REFRESH_COOKIE: refresh_1,
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["sessions_revoked"] == 2

    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE: refresh_2},
    )
    assert refresh_response.status_code == 401


async def test_session_list_excludes_revoked_and_expired(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _create_verified_user(db_session, "sessions@example.com")
    access, refresh = await _login_user(client, user.email, "StrongPassword1!")

    await client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE: refresh},
    )

    response = await client.get(
        "/api/v1/auth/sessions",
        cookies={settings.ACCESS_COOKIE: access},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert len(data["sessions"]) == 1


async def test_is_current_flag_correctly_identified(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _create_verified_user(db_session, "current@example.com")
    _, refresh = await _login_user(client, user.email, "StrongPassword1!")

    rotate_response = await client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE: refresh},
    )
    new_refresh = rotate_response.cookies.get(settings.REFRESH_COOKIE)
    access = rotate_response.cookies.get(settings.ACCESS_COOKIE)
    assert new_refresh is not None
    assert access is not None

    response = await client.get(
        "/api/v1/auth/sessions",
        cookies={
            settings.ACCESS_COOKIE: access,
            settings.REFRESH_COOKIE: new_refresh,
        },
    )
    assert response.status_code == 200
    sessions = response.json()["data"]["sessions"]
    current_sessions = [s for s in sessions if s["is_current"]]
    assert len(current_sessions) == 1


async def test_security_email_dispatched_on_reuse_detection(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _create_verified_user(db_session, "alert@example.com")
    _, refresh = await _login_user(client, user.email, "StrongPassword1!")

    rotate_response = await client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE: refresh},
    )
    assert rotate_response.status_code == 200

    token_hash = hash_token(refresh)
    result = await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    token_obj = result.scalars().first()
    assert token_obj is not None
    token_obj.last_used_at = datetime.now(UTC) - timedelta(
        seconds=settings.REFRESH_REUSE_GRACE_SECONDS + 10
    )
    await db_session.commit()

    with patch(
        "app.services.auth.send_security_alert_email", new_callable=AsyncMock
    ) as mock_alert:
        await client.post(
            "/api/v1/auth/refresh",
            cookies={settings.REFRESH_COOKIE: refresh},
        )
        for _ in range(int(ASYNC_SLEEP_SECONDS / 0.01)):
            if mock_alert.called:
                break
            await asyncio.sleep(0.01)
        mock_alert.assert_called_once()


async def test_security_email_failure_does_not_rollback_revocation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _create_verified_user(db_session, "alertfail@example.com")
    _, refresh = await _login_user(client, user.email, "StrongPassword1!")

    rotate_response = await client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE: refresh},
    )
    new_refresh = rotate_response.cookies.get(settings.REFRESH_COOKIE)
    assert new_refresh is not None

    token_hash = hash_token(refresh)
    result = await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    token_obj = result.scalars().first()
    assert token_obj is not None
    token_obj.last_used_at = datetime.now(UTC) - timedelta(
        seconds=settings.REFRESH_REUSE_GRACE_SECONDS + 10
    )
    await db_session.commit()

    with patch(
        "app.services.auth.send_security_alert_email",
        side_effect=Exception("SMTP down"),
    ):
        response = await client.post(
            "/api/v1/auth/refresh",
            cookies={settings.REFRESH_COOKIE: refresh},
        )
    assert response.status_code == 401

    follow_up = await client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE: new_refresh},
    )
    assert follow_up.status_code == 401
