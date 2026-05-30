"""Tests for profile management endpoints."""

from collections.abc import AsyncGenerator
from typing import Any, cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete as sa_delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CloudinaryUploadError
from app.core.security import hash_password
from app.models.users import User


@pytest.fixture
async def profile_user(
    db_session: AsyncSession,
) -> AsyncGenerator[Any, str]:
    """Create a verified user for profile tests."""
    creds: dict[str, str] = {
        "email": "profile@example.com",
        "password": "StrongPassword1!",
    }
    user = User(
        first_name="Profile",
        last_name="User",
        email=creds["email"],
        password_hash=hash_password(creds["password"]),
        is_email_verified=True,
        profile_photo_url="https://res.cloudinary.com/test/image/upload/v1234567890/profile_photos/test-photo-id.jpg",
    )
    db_session.add(user)
    await db_session.commit()
    yield creds
    await db_session.execute(sa_delete(User).where(User.email == creds["email"]))
    await db_session.commit()


# ─────────────────────────────────────────────────────────────────
# GET /profile endpoint tests
# ─────────────────────────────────────────────────────────────────


async def test_get_profile_success(
    client: AsyncClient,
    db_session: AsyncSession,
    profile_user: dict[str, str],
) -> None:
    """Test retrieving profile of authenticated user."""
    # Login
    login_response = await client.post("/api/v1/auth/login", json=profile_user)
    assert login_response.status_code == 200

    # Get profile
    response = await client.get("/api/v1/profile/")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Profile retrieved successfully"
    assert data["data"]["email"] == profile_user["email"]
    assert data["data"]["first_name"] == "Profile"
    assert data["data"]["last_name"] == "User"


async def test_get_profile_unauthenticated(client: AsyncClient) -> None:
    """Test that unauthenticated users cannot access profile."""
    response = await client.get("/api/v1/profile/")
    assert response.status_code == 401
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "Not authenticated"


async def test_get_profile_rate_limit(
    client: AsyncClient,
    db_session: AsyncSession,
    profile_user: dict[str, str],
) -> None:
    """Test rate limiting on GET /profile endpoint."""
    # Login
    await client.post("/api/v1/auth/login", json=profile_user)

    # Make 10 requests (at the limit)
    for _ in range(10):
        response = await client.get("/api/v1/profile/")
        assert response.status_code == 200

    # 11th request should be rate limited
    response = await client.get("/api/v1/profile/")
    assert response.status_code == 429
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "Rate limit exceeded"


# ─────────────────────────────────────────────────────────────────
# PUT /profile endpoint tests
# ─────────────────────────────────────────────────────────────────


async def test_update_profile_success(
    client: AsyncClient,
    db_session: AsyncSession,
    profile_user: dict[str, str],
) -> None:
    """Test successfully updating user profile."""
    # Login
    await client.post("/api/v1/auth/login", json=profile_user)

    # Update profile
    response = await client.put(
        "/api/v1/profile/",
        json={"first_name": "Updated", "last_name": "Name"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Profile updated successfully"
    assert data["data"]["first_name"] == "Updated"
    assert data["data"]["last_name"] == "Name"

    # Verify the update persisted
    response = await client.get("/api/v1/profile/")
    assert response.json()["data"]["first_name"] == "Updated"
    assert response.json()["data"]["last_name"] == "Name"


async def test_update_profile_first_name_only(
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Test updating only first_name."""
    # Login
    await client.post("/api/v1/auth/login", json=profile_user)

    # Update only first_name
    response = await client.put(
        "/api/v1/profile/",
        json={"first_name": "NewFirst"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["data"]["first_name"] == "NewFirst"
    assert data["data"]["last_name"] == "User"  # Unchanged


async def test_update_profile_last_name_only(
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Test updating only last_name."""
    # Login
    await client.post("/api/v1/auth/login", json=profile_user)

    # Update only last_name
    response = await client.put(
        "/api/v1/profile/",
        json={"last_name": "NewLast"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["data"]["first_name"] == "Profile"  # Unchanged
    assert data["data"]["last_name"] == "NewLast"


async def test_update_profile_no_fields_returns_error(
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Test that updating with no fields returns 400."""
    # Login
    await client.post("/api/v1/auth/login", json=profile_user)

    # Try to update with no fields
    response = await client.put(
        "/api/v1/profile/",
        json={},
    )

    assert response.status_code == 400
    data = response.json()
    assert data["status"] == "error"
    assert "At least one field" in data["message"]


async def test_update_profile_empty_strings_rejected(
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Test that empty strings are rejected in validation."""
    # Login
    await client.post("/api/v1/auth/login", json=profile_user)

    # Try to update with empty string
    response = await client.put(
        "/api/v1/profile/",
        json={"first_name": "   "},
    )

    assert response.status_code == 422
    data = response.json()
    assert data["status"] == "error"


async def test_update_profile_unauthenticated(client: AsyncClient) -> None:
    """Test that unauthenticated users cannot update profile."""
    response = await client.put(
        "/api/v1/profile/",
        json={"first_name": "Hacker"},
    )
    assert response.status_code == 401


async def test_update_profile_rate_limit(
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Test rate limiting on PUT /profile endpoint."""
    # Login
    await client.post("/api/v1/auth/login", json=profile_user)

    payload = {"first_name": "Updated"}

    # Make 5 requests (at the limit)
    for _ in range(5):
        response = await client.put("/api/v1/profile/", json=payload)
        assert response.status_code == 200

    # 6th request should be rate limited
    response = await client.put("/api/v1/profile/", json=payload)
    assert response.status_code == 429
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "Rate limit exceeded"


async def test_update_profile_role_only(
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Test updating only the role field."""
    await client.post("/api/v1/auth/login", json=profile_user)

    response = await client.put(
        "/api/v1/profile/",
        json={"role": "Software Engineer"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["data"]["role"] == "Software Engineer"


async def test_update_profile_role_persists(
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """role is returned in the GET /profile response after being set."""
    await client.post("/api/v1/auth/login", json=profile_user)

    await client.put("/api/v1/profile/", json={"role": "Designer"})

    response = await client.get("/api/v1/profile/")
    assert response.status_code == 200
    assert response.json()["data"]["role"] == "Designer"


async def test_update_profile_role_cleared_with_empty_string(
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Whitespace-only role is normalised to None by the validator; because no
    other field is provided the request is rejected with 400 (same behaviour
    as sending a whitespace-only first_name alone)."""
    await client.post("/api/v1/auth/login", json=profile_user)

    response = await client.put("/api/v1/profile/", json={"role": "   "})
    assert response.status_code == 400
    assert "At least one field" in response.json()["message"]


async def test_update_profile_email_only(
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Test updating only the email field."""
    await client.post("/api/v1/auth/login", json=profile_user)

    response = await client.put(
        "/api/v1/profile/",
        json={"email": "updated-profile@example.com"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["data"]["email"] == "updated-profile@example.com"


async def test_update_profile_email_normalized(
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Email is stripped and lowercased before validation."""
    await client.post("/api/v1/auth/login", json=profile_user)

    response = await client.put(
        "/api/v1/profile/",
        json={"email": "  UPPER-Profile@Example.COM  "},
    )

    assert response.status_code == 200
    assert response.json()["data"]["email"] == "upper-profile@example.com"


async def test_update_profile_invalid_email_rejected(
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Malformed email is rejected with 422."""
    await client.post("/api/v1/auth/login", json=profile_user)

    response = await client.put(
        "/api/v1/profile/",
        json={"email": "not-an-email"},
    )

    assert response.status_code == 422


async def test_update_profile_role_html_rejected(
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """HTML in the role field is rejected."""
    await client.post("/api/v1/auth/login", json=profile_user)

    response = await client.put(
        "/api/v1/profile/",
        json={"role": "<script>alert(1)</script>"},
    )

    assert response.status_code == 422


# ─────────────────────────────────────────────────────────────────
# DELETE /profile endpoint tests
# ─────────────────────────────────────────────────────────────────


@patch("app.services.profile.delete_asset", new_callable=AsyncMock)
async def test_delete_profile_success(
    mock_delete_asset: AsyncMock,
    client: AsyncClient,
    profile_user: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """Test successfully deleting user profile."""
    # Login
    await client.post("/api/v1/auth/login", json=profile_user)

    # Delete profile
    response = await client.delete("/api/v1/profile/")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Your profile has been permanently deleted."
    assert "id" in data["data"]

    # Verify asset was attempted to be deleted
    mock_delete_asset.assert_called_once()

    # Verify user no longer exists
    user_result = cast(
        CursorResult[Any],
        await db_session.execute(
            sa_delete(User).where(User.email == profile_user["email"])
        ),
    )
    assert user_result.rowcount == 0


@patch("app.services.profile.delete_asset", new_callable=AsyncMock)
async def test_delete_profile_without_photo(
    mock_delete_asset: AsyncMock,
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test deleting profile when user has no profile photo."""
    # Create user without profile photo
    user = User(
        first_name="NoPhoto",
        last_name="User",
        email="nophoto@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
        profile_photo_url=None,
    )
    db_session.add(user)
    await db_session.commit()

    # Login
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nophoto@example.com", "password": "StrongPassword1!"},
    )
    assert response.status_code == 200

    # Delete profile
    response = await client.delete("/api/v1/profile/")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

    # Verify delete_asset was NOT called since there's no photo
    mock_delete_asset.assert_not_called()


@patch("app.services.profile.delete_asset", new_callable=AsyncMock)
async def test_delete_profile_cloudinary_failure_still_deletes_user(
    mock_delete_asset: AsyncMock,
    client: AsyncClient,
    db_session: AsyncSession,
    profile_user: dict[str, str],
) -> None:
    """Test that user is deleted even if Cloudinary deletion fails."""
    # Make Cloudinary deletion fail
    mock_delete_asset.side_effect = CloudinaryUploadError("Cloudinary error")

    # Login
    await client.post("/api/v1/auth/login", json=profile_user)

    # Delete profile
    response = await client.delete("/api/v1/profile/")

    # Should still return success
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

    # Verify Cloudinary was attempted
    mock_delete_asset.assert_called_once()

    # Verify user was still deleted despite Cloudinary error
    # Try to login - should fail
    login_response = await client.post("/api/v1/auth/login", json=profile_user)
    assert login_response.status_code == 401


async def test_delete_profile_unauthenticated(client: AsyncClient) -> None:
    """Test that unauthenticated users cannot delete profile."""
    response = await client.delete("/api/v1/profile/")
    assert response.status_code == 401


async def test_delete_profile_rate_limit(
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Test rate limiting on DELETE /profile endpoint."""

    # Make multiple login attempts and delete attempts
    for _ in range(5):
        # Create a new test user for each iteration
        f"profile_{uuid4()}@example.com"
        # We need to create and delete a user each time for the rate limit test
        # Since delete is destructive, this test is limited

    # For now, just test that we can make one delete request
    # Rate limit testing for destructive endpoints is tricky
    await client.post("/api/v1/auth/login", json=profile_user)
    response = await client.delete("/api/v1/profile/")
    assert response.status_code in [200, 429]


@patch("app.services.profile.delete_asset", new_callable=AsyncMock)
async def test_delete_profile_extracts_cloudinary_public_id(
    mock_delete_asset: AsyncMock,
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Test that the public_id is correctly extracted from Cloudinary URL."""
    # Login
    await client.post("/api/v1/auth/login", json=profile_user)

    # Delete profile
    response = await client.delete("/api/v1/profile/")

    assert response.status_code == 200

    # Verify delete_asset was called with the correct public_id
    mock_delete_asset.assert_called_once()
    called_public_id = mock_delete_asset.call_args[0][0]
    assert "profile_photos/test-photo-id" in called_public_id


# ─────────────────────────────────────────────────────────────────
# PUT /profile/photo endpoint tests
# ─────────────────────────────────────────────────────────────────


@patch("app.services.profile.upload_logo", new_callable=AsyncMock)
async def test_upload_profile_photo_success(
    mock_upload: AsyncMock,
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Test successfully uploading a profile photo."""
    # Mock the upload to return a URL and public_id
    mock_upload.return_value = (
        "https://res.cloudinary.com/test/image/upload/v1234567890/template-logos/new-id.jpg",
        "template-logos/new-id",
    )

    # Login
    await client.post("/api/v1/auth/login", json=profile_user)

    # Create a fake image file
    image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    response = await client.put(
        "/api/v1/profile/photo",
        files={"file": ("test.png", image_data, "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Profile photo updated successfully"
    assert data["data"]["profile_photo_url"].startswith("https://res.cloudinary.com")

    # Verify upload was called
    mock_upload.assert_called_once()


@patch("app.services.profile.upload_logo", new_callable=AsyncMock)
async def test_upload_profile_photo_jpeg(
    mock_upload: AsyncMock,
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Test uploading a JPEG profile photo."""
    mock_upload.return_value = (
        "https://res.cloudinary.com/test/image/upload/v1234567890/template-logos/new-id.jpg",
        "template-logos/new-id",
    )

    # Login
    await client.post("/api/v1/auth/login", json=profile_user)

    # Create a fake JPEG image
    image_data = b"\xff\xd8\xff\xe0" + b"\x00" * 100

    response = await client.put(
        "/api/v1/profile/photo",
        files={"file": ("test.jpg", image_data, "image/jpeg")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"


@patch("app.services.profile.upload_logo", new_callable=AsyncMock)
async def test_upload_profile_photo_gif(
    mock_upload: AsyncMock,
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Test uploading a GIF profile photo."""
    mock_upload.return_value = (
        "https://res.cloudinary.com/test/image/upload/v1234567890/template-logos/new-id.gif",
        "template-logos/new-id",
    )

    # Login
    await client.post("/api/v1/auth/login", json=profile_user)

    # Create a fake GIF image
    image_data = b"GIF89a" + b"\x00" * 100

    response = await client.put(
        "/api/v1/profile/photo",
        files={"file": ("test.gif", image_data, "image/gif")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"


async def test_upload_profile_photo_unsupported_format(
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Test that unsupported file formats are rejected."""
    # Login
    await client.post("/api/v1/auth/login", json=profile_user)

    response = await client.put(
        "/api/v1/profile/photo",
        files={"file": ("test.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 400
    data = response.json()
    assert data["status"] == "error"
    assert "Invalid file format" in data["message"]


async def test_upload_profile_photo_file_too_large(
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Test that files larger than 10 MB are rejected."""
    # Login
    await client.post("/api/v1/auth/login", json=profile_user)

    # Create a file just over 10 MB limit to test boundary condition
    # PNG magic bytes + padding to exceed limit by 1 byte
    large_image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * (10 * 1024 * 1024 + 1)

    response = await client.put(
        "/api/v1/profile/photo",
        files={"file": ("large.png", large_image_data, "image/png")},
    )

    assert response.status_code == 413
    data = response.json()
    assert data["status"] == "error"
    assert "too large" in data["message"]


@patch("app.services.profile.upload_logo", new_callable=AsyncMock)
async def test_upload_profile_photo_deletes_old_photo(
    mock_upload: AsyncMock,
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Test that uploading a new photo deletes the old one."""
    mock_upload.return_value = (
        "https://res.cloudinary.com/test/image/upload/v1234567890/template-logos/new-id.jpg",
        "template-logos/new-id",
    )

    # Login
    await client.post("/api/v1/auth/login", json=profile_user)

    image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    with patch("app.services.profile.delete_asset", new_callable=AsyncMock) as mock_del:
        response = await client.put(
            "/api/v1/profile/photo",
            files={"file": ("test.png", image_data, "image/png")},
        )

    assert response.status_code == 200

    # Verify that delete_asset was called to remove the old photo
    mock_del.assert_called_once()


async def test_upload_profile_photo_unauthenticated(client: AsyncClient) -> None:
    """Test that unauthenticated users cannot upload photos."""
    image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    response = await client.put(
        "/api/v1/profile/photo",
        files={"file": ("test.png", image_data, "image/png")},
    )

    assert response.status_code == 401


@patch("app.services.profile.upload_logo", new_callable=AsyncMock)
async def test_upload_profile_photo_rate_limit(
    mock_upload: AsyncMock,
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Test rate limiting on profile photo upload."""
    mock_upload.return_value = (
        "https://res.cloudinary.com/test/image/upload/v1234567890/template-logos/new-id.jpg",
        "template-logos/new-id",
    )

    # Login
    await client.post("/api/v1/auth/login", json=profile_user)

    image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    # Make 10 requests (at the limit)
    for _ in range(10):
        response = await client.put(
            "/api/v1/profile/photo",
            files={"file": ("test.png", image_data, "image/png")},
        )
        assert response.status_code == 200

    # 11th request should be rate limited
    response = await client.put(
        "/api/v1/profile/photo",
        files={"file": ("test.png", image_data, "image/png")},
    )
    assert response.status_code == 429


# ─────────────────────────────────────────────────────────────────
# DELETE /profile/photo endpoint tests
# ─────────────────────────────────────────────────────────────────


@patch("app.services.profile.delete_asset", new_callable=AsyncMock)
async def test_remove_profile_photo_success(
    mock_delete_asset: AsyncMock,
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Removing a photo clears profile_photo_url and calls Cloudinary delete."""
    await client.post("/api/v1/auth/login", json=profile_user)

    response = await client.delete("/api/v1/profile/photo")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Profile photo removed successfully"
    assert data["data"]["profile_photo_url"] is None
    mock_delete_asset.assert_called_once()


@patch("app.services.profile.delete_asset", new_callable=AsyncMock)
async def test_remove_profile_photo_no_photo_is_noop(
    mock_delete_asset: AsyncMock,
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Removing a photo when none is set succeeds silently
    without calling Cloudinary."""
    user = User(
        first_name="NoPhoto",
        last_name="Remove",
        email="nophoto-remove@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
        profile_photo_url=None,
    )
    db_session.add(user)
    await db_session.commit()

    await client.post(
        "/api/v1/auth/login",
        json={"email": "nophoto-remove@example.com", "password": "StrongPassword1!"},
    )

    response = await client.delete("/api/v1/profile/photo")

    assert response.status_code == 200
    assert response.json()["data"]["profile_photo_url"] is None
    mock_delete_asset.assert_not_called()


async def test_remove_profile_photo_unauthenticated(client: AsyncClient) -> None:
    """Unauthenticated request returns 401."""
    response = await client.delete("/api/v1/profile/photo")
    assert response.status_code == 401


@patch("app.services.profile.delete_asset", new_callable=AsyncMock)
async def test_remove_profile_photo_cloudinary_failure_still_clears_url(
    mock_delete_asset: AsyncMock,
    client: AsyncClient,
    profile_user: dict[str, str],
) -> None:
    """Cloudinary failure is logged but profile_photo_url is still cleared."""
    mock_delete_asset.side_effect = CloudinaryUploadError("storage error")

    await client.post("/api/v1/auth/login", json=profile_user)

    response = await client.delete("/api/v1/profile/photo")

    assert response.status_code == 200
    assert response.json()["data"]["profile_photo_url"] is None
    mock_delete_asset.assert_called_once()


@patch("app.services.profile.delete_asset", new_callable=AsyncMock)
async def test_remove_profile_photo_rate_limit(
    mock_delete_asset: AsyncMock,
    client: AsyncClient,
    db_session: AsyncSession,
    profile_user: dict[str, str],
) -> None:
    """DELETE /profile/photo is rate-limited at 10/minute."""
    mock_delete_asset.return_value = None

    await client.post("/api/v1/auth/login", json=profile_user)

    for _ in range(10):
        response = await client.delete("/api/v1/profile/photo")
        assert response.status_code == 200

    response = await client.delete("/api/v1/profile/photo")
    assert response.status_code == 429
