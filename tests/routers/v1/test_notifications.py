from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.users import User


@pytest.fixture
async def notifications_user(
    db_session: AsyncSession,
) -> AsyncGenerator[dict[str, str]]:
    """Create a verified user for notifications tests."""
    creds = {
        "email": "organiser_notifications@example.com",
        "password": "StrongPassword1!",
    }
    user = User(
        first_name="Organiser",
        last_name="Notifications",
        email=creds["email"],
        password_hash=hash_password(creds["password"]),
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    yield creds
    await db_session.execute(sa_delete(User).where(User.email == creds["email"]))
    await db_session.commit()


# ─────────────────────────────────────────────────────────────────
# GET /api/v1/organiser/notifications
# ─────────────────────────────────────────────────────────────────


async def test_get_returns_defaults_for_new_organiser(
    client: AsyncClient,
    notifications_user: dict[str, str],
) -> None:
    """A new organiser who has never saved preferences receives default values."""
    # Login
    login_response = await client.post("/api/v1/auth/login", json=notifications_user)
    assert login_response.status_code == 200

    # Get notification preferences
    response = await client.get("/api/v1/organiser/notifications")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Notification preferences retrieved successfully."
    assert data["data"]["email_template_published"] is True
    assert data["data"]["email_new_signin"] is True
    assert data["data"]["updated_at"] is None


async def test_get_returns_saved_preferences(
    client: AsyncClient,
    notifications_user: dict[str, str],
) -> None:
    """GET returns updated preferences after they are saved via PATCH."""
    # Login
    await client.post("/api/v1/auth/login", json=notifications_user)

    # Disable email_template_published
    patch_response = await client.patch(
        "/api/v1/organiser/notifications",
        json={"email_template_published": False},
    )
    assert patch_response.status_code == 200

    # Retrieve preferences and verify they changed
    get_response = await client.get("/api/v1/organiser/notifications")
    assert get_response.status_code == 200

    data = get_response.json()
    assert data["data"]["email_template_published"] is False
    assert data["data"]["email_new_signin"] is True
    assert data["data"]["updated_at"] is not None


async def test_get_unauthenticated_returns_401(client: AsyncClient) -> None:
    """An unauthenticated request to GET returns 401."""
    response = await client.get("/api/v1/organiser/notifications")
    assert response.status_code == 401
    assert response.json()["status"] == "error"
    assert response.json()["message"] == "Not authenticated"


async def test_get_returns_correct_field_names(
    client: AsyncClient,
    notifications_user: dict[str, str],
) -> None:
    """GET returns responses containing the expected keys."""
    await client.post("/api/v1/auth/login", json=notifications_user)

    response = await client.get("/api/v1/organiser/notifications")
    assert response.status_code == 200

    data = response.json()["data"]
    # Ensure expected keys are present
    assert "email_template_published" in data
    assert "email_new_signin" in data
    assert "updated_at" in data


# ─────────────────────────────────────────────────────────────────
# PATCH /api/v1/organiser/notifications
# ─────────────────────────────────────────────────────────────────


async def test_patch_updates_single_field(
    client: AsyncClient,
    notifications_user: dict[str, str],
) -> None:
    """PATCH updates only the specified field and leaves others at default."""
    await client.post("/api/v1/auth/login", json=notifications_user)

    # Disable only email_new_signin
    response = await client.patch(
        "/api/v1/organiser/notifications",
        json={"email_new_signin": False},
    )
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["email_new_signin"] is False
    assert data["email_template_published"] is True  # still True


async def test_patch_updates_both_fields(
    client: AsyncClient,
    notifications_user: dict[str, str],
) -> None:
    """PATCH updates multiple fields simultaneously."""
    await client.post("/api/v1/auth/login", json=notifications_user)

    response = await client.patch(
        "/api/v1/organiser/notifications",
        json={"email_new_signin": False, "email_template_published": False},
    )
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["email_new_signin"] is False
    assert data["email_template_published"] is False


async def test_patch_unrecognized_keys_ignored(
    client: AsyncClient,
    notifications_user: dict[str, str],
) -> None:
    """Unrecognized keys in the PATCH request body are ignored
    and valid fields are updated."""
    await client.post("/api/v1/auth/login", json=notifications_user)

    response = await client.patch(
        "/api/v1/organiser/notifications",
        json={
            "email_new_signin": False,
            "unknown_field_123": True,
            "another_bad_field": "hello",
        },
    )
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["email_new_signin"] is False
    assert data["email_template_published"] is True  # still default True
    assert "unknown_field_123" not in data
    assert "another_bad_field" not in data


async def test_patch_empty_body_returns_400(
    client: AsyncClient,
    notifications_user: dict[str, str],
) -> None:
    """PATCH with an empty body `{}` returns 400."""
    await client.post("/api/v1/auth/login", json=notifications_user)

    response = await client.patch(
        "/api/v1/organiser/notifications",
        json={},
    )
    assert response.status_code == 400
    assert response.json()["status"] == "error"
    assert "at least one preference field" in response.json()["message"].lower()


async def test_patch_unauthenticated_returns_401(client: AsyncClient) -> None:
    """An unauthenticated request to PATCH returns 401."""
    response = await client.patch(
        "/api/v1/organiser/notifications",
        json={"email_new_signin": False},
    )
    assert response.status_code == 401
    assert response.json()["status"] == "error"


async def test_patch_no_body_returns_400(
    client: AsyncClient,
    notifications_user: dict[str, str],
) -> None:
    """PATCH with no body returns 400."""
    await client.post("/api/v1/auth/login", json=notifications_user)

    response = await client.patch(
        "/api/v1/organiser/notifications",
    )
    assert response.status_code == 400
    assert response.json()["status"] == "error"
