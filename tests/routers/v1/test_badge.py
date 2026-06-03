import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.core.token import create_access_token
from app.models import Badge, BadgeHashtag, PlatformTemplate, User


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a verified user for authenticated requests."""
    user = User(
        first_name="Test",
        last_name="Organiser",
        email="organiser@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_cookies(test_user: User) -> dict[str, str]:
    """Return a cookie dictionary for the test user."""
    token = create_access_token(test_user.id)
    return {settings.ACCESS_COOKIE: token}


@pytest.fixture
async def platform_template(db_session: AsyncSession) -> PlatformTemplate:
    """Seed a single platform template for tests."""
    template = PlatformTemplate(
        title="Test Layout",
        category="Test Category",
        canvas_data={"layout": "test-v1"},
        thumbnail_url=None,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


async def test_create_instance_success(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    platform_template: PlatformTemplate,
    test_user: User,
) -> None:
    response = await client.post(
        "/api/v1/badges",
        cookies=auth_cookies,
        json={"platform_template_id": str(platform_template.id)},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Badge created successfully."
    assert data["data"]["platform_template_id"] == str(platform_template.id)
    assert data["data"]["organiser_id"] == str(test_user.id)
    assert "id" in data["data"]
    assert "created_at" in data["data"]


async def test_create_instance_unauthenticated(
    client: AsyncClient, platform_template: PlatformTemplate
) -> None:
    response = await client.post(
        "/api/v1/badges",
        json={"platform_template_id": str(platform_template.id)},
    )
    assert response.status_code in (401, 403)


async def test_create_instance_platform_template_not_found(
    client: AsyncClient, auth_cookies: dict[str, str]
) -> None:
    fake_id = uuid.uuid4()
    response = await client.post(
        "/api/v1/badges",
        cookies=auth_cookies,
        json={"platform_template_id": str(fake_id)},
    )
    assert response.status_code == 404
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "Platform template not found."


async def test_create_instance_missing_field(
    client: AsyncClient, auth_cookies: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/badges",
        cookies=auth_cookies,
        json={},
    )
    assert response.status_code == 422


@pytest.fixture
async def badge(
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> Badge:
    """Seed an badge owned by test_user."""
    template = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="My Test Event",
        canvas_data={"layout": "test-v1"},
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


async def test_publish_template_success(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    badge: Badge,
) -> None:
    response = await client.post(
        f"/api/v1/badges/{badge.id}/publish",
        cookies=auth_cookies,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Badge published successfully."
    assert data["data"]["is_published"] is True
    assert data["data"]["share_slug"] is not None
    assert len(data["data"]["share_slug"]) == 12
    assert data["data"]["published_at"] is not None


async def test_publish_template_unauthenticated(
    client: AsyncClient, badge: Badge
) -> None:
    response = await client.post(
        f"/api/v1/badges/{badge.id}/publish",
    )
    assert response.status_code in (401, 403)


async def test_publish_template_not_found(
    client: AsyncClient, auth_cookies: dict[str, str]
) -> None:
    fake_id = uuid.uuid4()
    response = await client.post(
        f"/api/v1/badges/{fake_id}/publish",
        cookies=auth_cookies,
    )
    assert response.status_code == 404
    assert response.json()["message"] == "Badge not found."


async def test_publish_template_not_owner(
    client: AsyncClient,
    db_session: AsyncSession,
    platform_template: PlatformTemplate,
) -> None:
    """A different user cannot publish someone else's template."""
    owner = User(
        first_name="Owner",
        last_name="User",
        email="owner@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    other = User(
        first_name="Other",
        last_name="User",
        email="other@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    db_session.add(owner)
    await db_session.flush()
    db_session.add(other)
    await db_session.flush()
    await db_session.commit()
    await db_session.refresh(owner)
    await db_session.refresh(other)

    template = Badge(
        organiser_id=owner.id,
        platform_template_id=platform_template.id,
        title="Owner's Event",
        canvas_data={"layout": "test-v1"},
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)

    other_token = create_access_token(other.id)
    response = await client.post(
        f"/api/v1/badges/{template.id}/publish",
        cookies={settings.ACCESS_COOKIE: other_token},
    )
    assert response.status_code == 403
    assert response.json()["message"] == "You do not own this badge."


async def test_publish_template_already_published(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    badge: Badge,
) -> None:
    await client.post(
        f"/api/v1/badges/{badge.id}/publish",
        cookies=auth_cookies,
    )
    response = await client.post(
        f"/api/v1/badges/{badge.id}/publish",
        cookies=auth_cookies,
    )
    assert response.status_code == 409
    assert response.json()["message"] == "Badge is already published."


async def test_unpublish_template_success(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    badge: Badge,
) -> None:
    publish_response = await client.post(
        f"/api/v1/badges/{badge.id}/publish",
        cookies=auth_cookies,
    )
    original_slug = publish_response.json()["data"]["share_slug"]

    response = await client.post(
        f"/api/v1/badges/{badge.id}/unpublish",
        cookies=auth_cookies,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Badge unpublished successfully."
    assert data["data"]["is_published"] is False
    assert data["data"]["share_slug"] == original_slug
    assert data["data"]["published_at"] is None


async def test_republish_preserves_slug(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    badge: Badge,
) -> None:
    first = await client.post(
        f"/api/v1/badges/{badge.id}/publish",
        cookies=auth_cookies,
    )
    original_slug = first.json()["data"]["share_slug"]

    await client.post(
        f"/api/v1/badges/{badge.id}/unpublish",
        cookies=auth_cookies,
    )
    second = await client.post(
        f"/api/v1/badges/{badge.id}/publish",
        cookies=auth_cookies,
    )
    assert second.status_code == 200
    assert second.json()["data"]["share_slug"] == original_slug


async def test_unpublish_template_not_found(
    client: AsyncClient, auth_cookies: dict[str, str]
) -> None:
    fake_id = uuid.uuid4()
    response = await client.post(
        f"/api/v1/badges/{fake_id}/unpublish",
        cookies=auth_cookies,
    )
    assert response.status_code == 404


# ── logo upload ───────────────────────────────────────────────────────────

# Minimal valid PNG/JPEG magic bytes so the endpoint's signature check passes.
_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
_FAKE_JPEG = b"\xff\xd8\xff" + b"\x00" * 8
_FAKE_URL = "https://res.cloudinary.com/demo/image/upload/template-logos/abc.png"
_FAKE_PUBLIC_ID = "template-logos/abc"


@pytest.fixture
async def template_instance(
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> Badge:
    """Organiser badge owned by test_user, no logo yet."""
    instance = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="My Template",
        canvas_data={},
    )
    db_session.add(instance)
    await db_session.commit()
    await db_session.refresh(instance)
    return instance


@pytest.fixture
async def template_instance_with_logo(
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> Badge:
    """Organiser badge that already has an uploaded logo."""
    instance = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="My Template With Logo",
        canvas_data={},
        logo_url="https://old-logo.example.com/logo.png",
        logo_public_id="template-logos/old-logo-id",
    )
    db_session.add(instance)
    await db_session.commit()
    await db_session.refresh(instance)
    return instance


@pytest.fixture
async def other_user(db_session: AsyncSession) -> User:
    """A second user who does NOT own the template_instance fixture."""
    user = User(
        first_name="Other",
        last_name="User",
        email="other-organiser@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def other_auth_cookies(other_user: User) -> dict[str, str]:
    token = create_access_token(other_user.id)
    return {settings.ACCESS_COOKIE: token}


@patch("app.services.badge.upload_logo", new_callable=AsyncMock)
async def test_upload_logo_success(
    mock_upload: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    template_instance: Badge,
) -> None:
    mock_upload.return_value = (_FAKE_URL, _FAKE_PUBLIC_ID)

    response = await client.put(
        f"/api/v1/badges/{template_instance.id}/logo",
        cookies=auth_cookies,
        files={"file": ("logo.png", _FAKE_PNG, "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Logo uploaded successfully."
    assert data["data"]["logo_url"] == _FAKE_URL
    mock_upload.assert_called_once_with(_FAKE_PNG)


@patch("app.services.badge.delete_logo", new_callable=AsyncMock)
@patch("app.services.badge.upload_logo", new_callable=AsyncMock)
async def test_upload_logo_replaces_existing(
    mock_upload: AsyncMock,
    mock_delete: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    template_instance_with_logo: Badge,
) -> None:
    """Uploading a new logo should delete the old Cloudinary asset first."""
    mock_upload.return_value = (_FAKE_URL, _FAKE_PUBLIC_ID)

    response = await client.put(
        f"/api/v1/badges/{template_instance_with_logo.id}/logo",
        cookies=auth_cookies,
        files={"file": ("logo.jpg", _FAKE_JPEG, "image/jpeg")},
    )

    assert response.status_code == 200
    mock_delete.assert_called_once_with("template-logos/old-logo-id")
    mock_upload.assert_called_once()


@patch("app.services.badge.upload_logo", new_callable=AsyncMock)
async def test_upload_logo_unsupported_type(
    mock_upload: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    template_instance: Badge,
) -> None:
    response = await client.put(
        f"/api/v1/badges/{template_instance.id}/logo",
        cookies=auth_cookies,
        files={"file": ("logo.gif", b"fake-gif-bytes", "image/gif")},
    )

    assert response.status_code == 415
    data = response.json()
    assert data["status"] == "error"
    mock_upload.assert_not_called()


@patch("app.services.badge.upload_logo", new_callable=AsyncMock)
async def test_upload_logo_too_large(
    mock_upload: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    template_instance: Badge,
) -> None:
    # PNG magic + enough padding to exceed 2 MB.
    oversized = _FAKE_PNG + b"x" * (2 * 1024 * 1024)

    response = await client.put(
        f"/api/v1/badges/{template_instance.id}/logo",
        cookies=auth_cookies,
        files={"file": ("logo.png", oversized, "image/png")},
    )

    assert response.status_code == 413
    data = response.json()
    assert data["status"] == "error"
    mock_upload.assert_not_called()


async def test_upload_logo_unauthenticated(
    client: AsyncClient,
    template_instance: Badge,
) -> None:
    response = await client.put(
        f"/api/v1/badges/{template_instance.id}/logo",
        files={"file": ("logo.png", _FAKE_PNG, "image/png")},
    )

    assert response.status_code in (401, 403)


@patch("app.services.badge.upload_logo", new_callable=AsyncMock)
async def test_upload_logo_instance_not_found(
    mock_upload: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
) -> None:
    response = await client.put(
        f"/api/v1/badges/{uuid.uuid4()}/logo",
        cookies=auth_cookies,
        files={"file": ("logo.png", _FAKE_PNG, "image/png")},
    )

    assert response.status_code == 404
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "Badge not found."
    mock_upload.assert_not_called()


async def test_upload_logo_forbidden(
    client: AsyncClient,
    other_auth_cookies: dict[str, str],
    template_instance: Badge,
) -> None:
    """A user who does not own the instance should get 403."""
    response = await client.put(
        f"/api/v1/badges/{template_instance.id}/logo",
        cookies=other_auth_cookies,
        files={"file": ("logo.png", _FAKE_PNG, "image/png")},
    )

    assert response.status_code == 403
    data = response.json()
    assert data["status"] == "error"


@patch("app.services.badge.upload_logo", new_callable=AsyncMock)
async def test_upload_logo_rejects_spoofed_mime_type(
    mock_upload: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    template_instance: Badge,
) -> None:
    """File declared as image/png but containing GIF magic bytes should be rejected."""
    gif_bytes = b"GIF89a" + b"\x00" * 20

    response = await client.put(
        f"/api/v1/badges/{template_instance.id}/logo",
        cookies=auth_cookies,
        files={"file": ("evil.png", gif_bytes, "image/png")},
    )

    assert response.status_code == 415
    mock_upload.assert_not_called()


@patch("app.services.badge.upload_logo", new_callable=AsyncMock)
async def test_upload_logo_soft_deleted_instance_returns_404(
    mock_upload: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    """A soft-deleted instance should be treated as not found."""
    from datetime import UTC, datetime

    deleted_instance = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Deleted Template",
        canvas_data={},
        deleted_at=datetime.now(UTC),
    )
    db_session.add(deleted_instance)
    await db_session.commit()
    await db_session.refresh(deleted_instance)

    response = await client.put(
        f"/api/v1/badges/{deleted_instance.id}/logo",
        cookies=auth_cookies,
        files={"file": ("logo.png", _FAKE_PNG, "image/png")},
    )

    assert response.status_code == 404
    mock_upload.assert_not_called()


@patch("app.services.badge.delete_logo", new_callable=AsyncMock)
@patch("app.services.badge.upload_logo", new_callable=AsyncMock)
async def test_upload_logo_uploads_before_deleting_old(
    mock_upload: AsyncMock,
    mock_delete: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    template_instance_with_logo: Badge,
) -> None:
    """New asset must be uploaded and persisted before the old one is deleted."""
    call_order: list[str] = []

    async def fake_upload(*args: object, **kwargs: object) -> tuple[str, str]:
        call_order.append("upload")
        return (_FAKE_URL, _FAKE_PUBLIC_ID)

    async def fake_delete(*args: object, **kwargs: object) -> None:
        call_order.append("delete")

    mock_upload.side_effect = fake_upload
    mock_delete.side_effect = fake_delete

    response = await client.put(
        f"/api/v1/badges/{template_instance_with_logo.id}/logo",
        cookies=auth_cookies,
        files={"file": ("logo.png", _FAKE_PNG, "image/png")},
    )

    assert response.status_code == 200
    assert call_order == ["upload", "delete"], (
        f"Expected upload before delete, got: {call_order}"
    )


@patch("app.services.badge.delete_logo", new_callable=AsyncMock)
@patch("app.services.badge.upload_logo", new_callable=AsyncMock)
async def test_upload_logo_rate_limit(
    mock_upload: AsyncMock,
    mock_delete: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    template_instance: Badge,
) -> None:
    mock_upload.return_value = (_FAKE_URL, _FAKE_PUBLIC_ID)

    url = f"/api/v1/badges/{template_instance.id}/logo"
    for _ in range(10):
        await client.put(
            url,
            cookies=auth_cookies,
            files={"file": ("logo.png", _FAKE_PNG, "image/png")},
        )

    response = await client.put(
        url,
        cookies=auth_cookies,
        files={"file": ("logo.png", _FAKE_PNG, "image/png")},
    )
    assert response.status_code == 429
    data = response.json()
    assert data["status"] == "error"


@pytest.fixture
async def published_template(
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> Badge:
    """Seed a published badge with a slug, logo, and hashtags."""

    template = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="HNG Tech Fest 2026",
        canvas_data={"layout": "bold-v1", "accent": "#FF5733"},
        logo_url="https://res.cloudinary.com/demo/image/upload/template-logos/fest.png",
        default_caption="I'm attending HNG Tech Fest 2026! 🚀",
        destination_link="https://techfest.example.com",
        is_published=True,
        share_slug="abcdef123456",
    )
    db_session.add(template)
    await db_session.flush()

    for tag in ["#HNGTechFest", "#2026"]:
        db_session.add(BadgeHashtag(badge_id=template.id, hashtag=tag))

    await db_session.commit()
    await db_session.refresh(template)
    return template


async def test_get_participant_page_success(
    client: AsyncClient,
    published_template: Badge,
) -> None:
    response = await client.get(
        f"/api/v1/badges/public/{published_template.share_slug}",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Badge data retrieved successfully."
    assert data["data"]["title"] == "HNG Tech Fest 2026"
    assert data["data"]["canvas_data"] == {"layout": "bold-v1", "accent": "#FF5733"}
    assert data["data"]["logo_url"] == (
        "https://res.cloudinary.com/demo/image/upload/template-logos/fest.png"
    )
    assert data["data"]["default_caption"] == "I'm attending HNG Tech Fest 2026! 🚀"
    assert data["data"]["destination_link"] == "https://techfest.example.com"
    assert sorted(data["data"]["hashtags"]) == ["#2026", "#HNGTechFest"]


async def test_get_participant_page_no_hashtags(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    """Published template with no hashtags should return an empty list."""
    template = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="No Tags Event",
        canvas_data={"layout": "minimal-v1"},
        is_published=True,
        share_slug="notags000001",
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)

    response = await client.get("/api/v1/badges/public/notags000001")
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["hashtags"] == []


async def test_get_participant_page_unpublished(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    """Slug exists but template is in draft state — should return 404."""
    template = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Draft Event",
        canvas_data={"layout": "test-v1"},
        is_published=False,
        share_slug="draft0000001",
    )
    db_session.add(template)
    await db_session.commit()

    response = await client.get("/api/v1/badges/public/draft0000001")
    assert response.status_code == 404
    assert response.json()["message"] == "Badge not found."


async def test_get_participant_page_nonexistent_slug(
    client: AsyncClient,
) -> None:
    """A completely random slug should return 404."""
    response = await client.get("/api/v1/badges/public/doesnotexist1")
    assert response.status_code == 404
    assert response.json()["message"] == "Badge not found."


async def test_get_participant_page_soft_deleted(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    """Published but soft-deleted template should return 404."""
    from datetime import UTC, datetime

    template = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Deleted Event",
        canvas_data={"layout": "test-v1"},
        is_published=True,
        share_slug="deleted00001",
        deleted_at=datetime.now(UTC),
    )
    db_session.add(template)
    await db_session.commit()

    response = await client.get("/api/v1/badges/public/deleted00001")
    assert response.status_code == 404
    assert response.json()["message"] == "Badge not found."


async def test_get_participant_page_no_auth_required(
    client: AsyncClient,
    published_template: Badge,
) -> None:
    """No Bearer token sent — should still return 200, not 401."""
    response = await client.get(
        f"/api/v1/badges/public/{published_template.share_slug}",
    )
    assert response.status_code == 200


async def test_get_participant_page_was_published_then_unpublished(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    """Slug that was once published but has since been unpublished returns 404."""
    template = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Past Event",
        canvas_data={"layout": "test-v1"},
        is_published=False,  # was published, now unpublished
        share_slug="waspub000001",  # slug preserved from when it was published
    )
    db_session.add(template)
    await db_session.commit()

    response = await client.get("/api/v1/badges/public/waspub000001")
    assert response.status_code == 404
    assert response.json()["message"] == "Badge not found."


# ── share_count / creation_count ──────────────────────────────────────────────


async def test_get_participant_page_does_not_increment_share_count(
    client: AsyncClient,
    db_session: AsyncSession,
    published_template: Badge,
) -> None:
    """GET /badges/public/{slug} should NOT increment share_count anymore.

    Share increments are now decoupled into the dedicated
    /badges/public/{slug}/increment-share endpoint, called explicitly by
    the FE on share actions.
    """
    assert published_template.share_count == 0

    await client.get(f"/api/v1/badges/public/{published_template.share_slug}")
    await db_session.refresh(published_template)
    assert published_template.share_count == 0

    await client.get(f"/api/v1/badges/public/{published_template.share_slug}")
    await db_session.refresh(published_template)
    assert published_template.share_count == 0


async def test_increment_share_success(
    client: AsyncClient,
    published_template: Badge,
) -> None:
    """POST /badges/public/{slug}/increment-share returns 200."""
    response = await client.post(
        f"/api/v1/badges/public/{published_template.share_slug}/increment-share"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "Share count increment scheduled" in data["message"]


async def test_increment_share_increments_count(
    client: AsyncClient,
    db_session: AsyncSession,
    published_template: Badge,
) -> None:
    """share_count increases by 1 for each POST call."""
    assert published_template.share_count == 0

    await client.post(
        f"/api/v1/badges/public/{published_template.share_slug}/increment-share"
    )
    await db_session.refresh(published_template)
    assert published_template.share_count == 1

    await client.post(
        f"/api/v1/badges/public/{published_template.share_slug}/increment-share"
    )
    await db_session.refresh(published_template)
    assert published_template.share_count == 2


async def test_increment_share_unpublished_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    """Unpublished badge slug returns 404."""
    template = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Draft Event",
        canvas_data={"layout": "test-v1"},
        is_published=False,
        share_slug="draftshare01",
    )
    db_session.add(template)
    await db_session.commit()

    response = await client.post("/api/v1/badges/public/draftshare01/increment-share")
    assert response.status_code == 404


async def test_increment_share_nonexistent_slug_returns_404(
    client: AsyncClient,
) -> None:
    response = await client.post("/api/v1/badges/public/doesnotexist99/increment-share")
    assert response.status_code == 404


async def test_increment_share_no_auth_required(
    client: AsyncClient,
    published_template: Badge,
) -> None:
    """No authentication required for the increment-share endpoint."""
    response = await client.post(
        f"/api/v1/badges/public/{published_template.share_slug}/increment-share"
    )
    assert response.status_code == 200


async def test_increment_creation_success(
    client: AsyncClient,
    published_template: Badge,
) -> None:
    """POST /badges/public/{slug}/increment-creation returns 200 success."""
    response = await client.post(
        f"/api/v1/badges/public/{published_template.share_slug}/increment-creation"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Creation count incremented."


async def test_increment_creation_increments_count(
    client: AsyncClient,
    db_session: AsyncSession,
    published_template: Badge,
) -> None:
    """creation_count increases by 1 for each POST call."""
    assert published_template.creation_count == 0

    await client.post(
        f"/api/v1/badges/public/{published_template.share_slug}/increment-creation"
    )
    await db_session.refresh(published_template)
    assert published_template.creation_count == 1

    await client.post(
        f"/api/v1/badges/public/{published_template.share_slug}/increment-creation"
    )
    await db_session.refresh(published_template)
    assert published_template.creation_count == 2


async def test_increment_creation_unpublished_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    """Unpublished badge slug returns 404 on the increment-creation endpoint."""
    template = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Draft Event",
        canvas_data={"layout": "test-v1"},
        is_published=False,
        share_slug="draftcreate01",
    )
    db_session.add(template)
    await db_session.commit()

    response = await client.post(
        "/api/v1/badges/public/draftcreate01/increment-creation"
    )
    assert response.status_code == 404
    assert response.json()["message"] == "Badge not found."


async def test_increment_creation_nonexistent_slug_returns_404(
    client: AsyncClient,
) -> None:
    """A completely unknown slug returns 404."""
    response = await client.post(
        "/api/v1/badges/public/doesnotexist99/increment-creation"
    )
    assert response.status_code == 404
    assert response.json()["message"] == "Badge not found."


async def test_increment_creation_no_auth_required(
    client: AsyncClient,
    published_template: Badge,
) -> None:
    """No authentication token required for the increment-creation endpoint."""
    response = await client.post(
        f"/api/v1/badges/public/{published_template.share_slug}/increment-creation"
    )
    assert response.status_code == 200


@pytest.fixture
async def seed_multiple_platform_templates(
    db_session: AsyncSession,
) -> list[PlatformTemplate]:
    """Seed multiple platform templates with different categories for tests."""
    templates = [
        PlatformTemplate(
            title="Alpha", category="festivals", canvas_data={"layout_id": "v1"}
        ),
        PlatformTemplate(
            title="Beta", category="festivals", canvas_data={"layout_id": "v1"}
        ),
        PlatformTemplate(
            title="Gamma", category="conferences", canvas_data={"layout_id": "v1"}
        ),
        PlatformTemplate(
            title="Delta", category="conferences", canvas_data={"layout_id": "v1"}
        ),
        PlatformTemplate(
            title="Epsilon", category="meetups", canvas_data={"layout_id": "v1"}
        ),
    ]
    for t in templates:
        db_session.add(t)
    await db_session.commit()
    for t in templates:
        await db_session.refresh(t)
    return templates


async def test_list_platform_templates_default_pagination(
    client: AsyncClient,
    seed_multiple_platform_templates: list[PlatformTemplate],
) -> None:
    response = await client.get("/api/v1/templates/platform")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Platform templates retrieved successfully."
    assert data["data"]["total"] == 5
    assert data["data"]["page"] == 1
    assert data["data"]["limit"] == 10
    assert len(data["data"]["templates"]) == 5
    assert data["data"]["prev"] is None
    assert data["data"]["next"] is None


async def test_list_platform_templates_custom_limit_page(
    client: AsyncClient,
    seed_multiple_platform_templates: list[PlatformTemplate],
) -> None:
    response = await client.get("/api/v1/templates/platform?page=2&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["total"] == 5
    assert data["data"]["page"] == 2
    assert data["data"]["limit"] == 2
    assert len(data["data"]["templates"]) == 2
    titles = [t["title"] for t in data["data"]["templates"]]
    assert titles == ["Alpha", "Beta"]
    assert data["data"]["prev"] == "/api/v1/templates/platform?page=1&limit=2"
    assert data["data"]["next"] == "/api/v1/templates/platform?page=3&limit=2"


async def test_list_platform_templates_category_filter(
    client: AsyncClient,
    seed_multiple_platform_templates: list[PlatformTemplate],
) -> None:
    response = await client.get(
        "/api/v1/templates/platform?category=conferences&page=1&limit=1"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["total"] == 2
    assert data["data"]["page"] == 1
    assert data["data"]["limit"] == 1
    assert len(data["data"]["templates"]) == 1
    assert data["data"]["templates"][0]["title"] == "Delta"
    assert data["data"]["prev"] is None
    assert (
        data["data"]["next"]
        == "/api/v1/templates/platform?page=2&limit=1&category=conferences"
    )


async def test_list_platform_templates_invalid_category(
    client: AsyncClient,
    seed_multiple_platform_templates: list[PlatformTemplate],
) -> None:
    response = await client.get("/api/v1/templates/platform?category=invalid_cat")
    assert response.status_code == 400
    data = response.json()
    assert data["status"] == "error"
    assert "Unknown category" in data["message"]


async def test_get_platform_template_success(
    client: AsyncClient,
    platform_template: PlatformTemplate,
) -> None:
    response = await client.get(f"/api/v1/templates/platform/{platform_template.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Platform template retrieved successfully."
    assert data["data"]["id"] == str(platform_template.id)
    assert data["data"]["title"] == platform_template.title


async def test_get_platform_template_not_found(
    client: AsyncClient,
) -> None:
    response = await client.get(f"/api/v1/templates/platform/{uuid.uuid4()}")
    assert response.status_code == 404
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "Platform template not found."


@pytest.fixture
async def source_for_duplicate(
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> Badge:
    """Badge with hashtags, used as the duplication source."""

    template = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Source Event",
        canvas_data={"layout_id": "photo_gradient_v1", "accent": "#3498DB"},
        default_caption="Attending Source Event!",
        destination_link="https://source.example.com",
        logo_url="https://cdn.example.com/logo.png",
        logo_public_id="template-logos/logo-src",
        access_type=0,
    )
    db_session.add(template)
    await db_session.flush()

    for tag in ["#SourceEvent", "#Tech"]:
        db_session.add(BadgeHashtag(badge_id=template.id, hashtag=tag))

    await db_session.commit()
    await db_session.refresh(template)
    return template


async def test_duplicate_template_success(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    source_for_duplicate: Badge,
    test_user: User,
) -> None:
    response = await client.post(
        f"/api/v1/badges/{source_for_duplicate.id}/duplicate",
        cookies=auth_cookies,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Badge duplicated successfully."
    assert data["data"]["id"] != str(source_for_duplicate.id)
    assert data["data"]["title"] == "Source Event (Copy)"
    assert data["data"]["organiser_id"] == str(test_user.id)
    assert data["data"]["platform_template_id"] == str(
        source_for_duplicate.platform_template_id
    )
    assert data["data"]["is_published"] is False
    assert data["data"]["created_at"] is not None


async def test_duplicate_template_copy_is_draft(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    source_for_duplicate: Badge,
) -> None:
    """The response must never carry a slug or published state."""
    response = await client.post(
        f"/api/v1/badges/{source_for_duplicate.id}/duplicate",
        cookies=auth_cookies,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["is_published"] is False
    assert "share_slug" not in data
    assert "published_at" not in data


async def test_duplicate_template_original_unchanged(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    source_for_duplicate: Badge,
) -> None:
    await client.post(
        f"/api/v1/badges/{source_for_duplicate.id}/duplicate",
        cookies=auth_cookies,
    )

    await db_session.refresh(source_for_duplicate)
    assert source_for_duplicate.title == "Source Event"


async def test_duplicate_template_unauthenticated(
    client: AsyncClient,
    source_for_duplicate: Badge,
) -> None:
    response = await client.post(
        f"/api/v1/badges/{source_for_duplicate.id}/duplicate",
    )

    assert response.status_code in (401, 403)


async def test_duplicate_template_not_found(
    client: AsyncClient,
    auth_cookies: dict[str, str],
) -> None:
    response = await client.post(
        f"/api/v1/badges/{uuid.uuid4()}/duplicate",
        cookies=auth_cookies,
    )

    assert response.status_code == 404
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "Badge not found."


async def test_duplicate_template_not_owner(
    client: AsyncClient,
    db_session: AsyncSession,
    platform_template: PlatformTemplate,
) -> None:
    from app.core.security import hash_password
    from app.core.token import create_access_token

    owner = User(
        first_name="Owner",
        last_name="User",
        email="dup-owner@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    db_session.add(owner)
    await db_session.flush()

    template = Badge(
        organiser_id=owner.id,
        platform_template_id=platform_template.id,
        title="Owner Only Event",
        canvas_data={"layout_id": "v1"},
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)

    other = User(
        first_name="Other",
        last_name="User",
        email="dup-other@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    other_token = create_access_token(other.id)
    response = await client.post(
        f"/api/v1/badges/{template.id}/duplicate",
        cookies={settings.ACCESS_COOKIE: other_token},
    )

    assert response.status_code == 403
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "You do not own this badge."


async def test_duplicate_soft_deleted_template_returns_404(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    from datetime import UTC, datetime

    deleted = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Gone Event",
        canvas_data={"layout_id": "v1"},
        deleted_at=datetime.now(UTC),
    )
    db_session.add(deleted)
    await db_session.commit()
    await db_session.refresh(deleted)

    response = await client.post(
        f"/api/v1/badges/{deleted.id}/duplicate",
        cookies=auth_cookies,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "Badge not found."


async def test_duplicate_published_template_copy_is_draft(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    from datetime import UTC, datetime

    published = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Live Event",
        canvas_data={"layout_id": "v1"},
        is_published=True,
        share_slug="live-slug-001",
        published_at=datetime.now(UTC),
    )
    db_session.add(published)
    await db_session.commit()
    await db_session.refresh(published)

    response = await client.post(
        f"/api/v1/badges/{published.id}/duplicate",
        cookies=auth_cookies,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["is_published"] is False


@pytest.fixture
async def badges_set(
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> list[Badge]:
    """Three templates: two drafts, one published."""
    from datetime import UTC, datetime

    draft_a = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Draft Alpha",
        canvas_data={"layout_id": "v1"},
        is_published=False,
    )
    draft_b = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Draft Beta",
        canvas_data={"layout_id": "v1"},
        is_published=False,
    )
    published = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Published Gamma",
        canvas_data={"layout_id": "v1"},
        is_published=True,
        share_slug="gamma-slug-01",
        published_at=datetime.now(UTC),
    )
    for t in [draft_a, draft_b, published]:
        db_session.add(t)

    await db_session.commit()
    for t in [draft_a, draft_b, published]:
        await db_session.refresh(t)

    return [draft_a, draft_b, published]


async def test_list_instances_success(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    badges_set: list[Badge],
) -> None:
    response = await client.get(
        "/api/v1/badges",
        cookies=auth_cookies,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Badges retrieved successfully."
    assert data["data"]["total"] == 3
    assert len(data["data"]["badges"]) == 3


async def test_list_instances_response_shape(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    badges_set: list[Badge],
) -> None:
    response = await client.get(
        "/api/v1/badges",
        cookies=auth_cookies,
    )

    item = response.json()["data"]["badges"][0]
    expected_keys = {
        "id",
        "title",
        "platform_template_id",
        "thumbnail_url",
        "is_published",
        "status",
        "share_slug",
        "published_at",
        "created_at",
        "updated_at",
        "total_shares",
        "total_badges_created",
    }
    assert expected_keys == set(item.keys())


async def test_list_instances_status_field_draft(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    badges_set: list[Badge],
) -> None:
    response = await client.get(
        "/api/v1/badges",
        cookies=auth_cookies,
    )

    items = response.json()["data"]["badges"]
    draft_items = [t for t in items if not t["is_published"]]
    assert all(t["status"] == "draft" for t in draft_items)


async def test_list_instances_status_field_published(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    badges_set: list[Badge],
) -> None:
    response = await client.get(
        "/api/v1/badges",
        cookies=auth_cookies,
    )

    items = response.json()["data"]["badges"]
    published_items = [t for t in items if t["is_published"]]
    assert all(t["status"] == "published" for t in published_items)


async def test_list_instances_canvas_data_not_exposed(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    badges_set: list[Badge],
) -> None:
    """canvas_data must not appear in the list response — it is large and unused."""
    response = await client.get(
        "/api/v1/badges",
        cookies=auth_cookies,
    )

    for item in response.json()["data"]["badges"]:
        assert "canvas_data" not in item


async def test_list_instances_empty_when_no_templates(
    client: AsyncClient,
    auth_cookies: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/badges",
        cookies=auth_cookies,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["badges"] == []
    assert data["total"] == 0
    assert data["prev"] is None
    assert data["next"] is None


async def test_list_instances_unauthenticated(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/badges")

    assert response.status_code in (401, 403)


async def test_list_instances_excludes_soft_deleted(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    from datetime import UTC, datetime

    live = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Live Template",
        canvas_data={"layout_id": "v1"},
    )
    deleted = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Deleted Template",
        canvas_data={"layout_id": "v1"},
        deleted_at=datetime.now(UTC),
    )
    db_session.add(live)
    db_session.add(deleted)
    await db_session.commit()

    response = await client.get(
        "/api/v1/badges",
        cookies=auth_cookies,
    )

    data = response.json()["data"]
    assert data["total"] == 1
    assert data["badges"][0]["title"] == "Live Template"


async def test_list_instances_only_returns_current_users_templates(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    from app.core.security import hash_password

    other = User(
        first_name="Other",
        last_name="Organiser",
        email="other-list-router@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    mine = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="My Template",
        canvas_data={"layout_id": "v1"},
    )
    theirs = Badge(
        organiser_id=other.id,
        platform_template_id=platform_template.id,
        title="Their Template",
        canvas_data={"layout_id": "v1"},
    )
    db_session.add(mine)
    db_session.add(theirs)
    await db_session.commit()

    response = await client.get(
        "/api/v1/badges",
        cookies=auth_cookies,
    )

    data = response.json()["data"]
    assert data["total"] == 1
    assert data["badges"][0]["title"] == "My Template"


async def test_list_instances_pagination_prev_next_links(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    for i in range(5):
        db_session.add(
            Badge(
                organiser_id=test_user.id,
                platform_template_id=platform_template.id,
                title=f"Event {i}",
                canvas_data={"layout_id": "v1"},
            )
        )
    await db_session.commit()

    response = await client.get(
        "/api/v1/badges?page=2&limit=2",
        cookies=auth_cookies,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["page"] == 2
    assert data["limit"] == 2
    assert data["total"] == 5
    assert len(data["badges"]) == 2
    assert "page=1" in data["prev"]
    assert "page=3" in data["next"]


async def test_list_instances_first_page_has_no_prev(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    for i in range(3):
        db_session.add(
            Badge(
                organiser_id=test_user.id,
                platform_template_id=platform_template.id,
                title=f"Event {i}",
                canvas_data={"layout_id": "v1"},
            )
        )
    await db_session.commit()

    response = await client.get(
        "/api/v1/badges?page=1&limit=2",
        cookies=auth_cookies,
    )

    data = response.json()["data"]
    assert data["prev"] is None
    assert data["next"] is not None


async def test_list_instances_last_page_has_no_next(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    for i in range(3):
        db_session.add(
            Badge(
                organiser_id=test_user.id,
                platform_template_id=platform_template.id,
                title=f"Event {i}",
                canvas_data={"layout_id": "v1"},
            )
        )
    await db_session.commit()

    response = await client.get(
        "/api/v1/badges?page=2&limit=2",
        cookies=auth_cookies,
    )

    data = response.json()["data"]
    assert data["next"] is None
    assert data["prev"] is not None


async def test_list_instances_invalid_page_param(
    client: AsyncClient,
    auth_cookies: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/badges?page=0",
        cookies=auth_cookies,
    )

    assert response.status_code == 422


async def test_list_instances_limit_exceeds_maximum(
    client: AsyncClient,
    auth_cookies: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/badges?limit=101",
        cookies=auth_cookies,
    )

    assert response.status_code == 422


@pytest.fixture
async def deletable_template(
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> Badge:
    template = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="To Be Deleted",
        canvas_data={"layout_id": "v1"},
        logo_url=(
            "https://res.cloudinary.com/mycloud/image/upload/"
            "template-logos/logo-del.png"
        ),
        logo_public_id="template-logos/logo-del",
    )
    db_session.add(template)
    await db_session.flush()

    await db_session.commit()
    await db_session.refresh(template)
    return template


@patch("app.services.badge.delete_logo", new_callable=AsyncMock)
async def test_delete_template_returns_204(
    _mock_logo: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    deletable_template: Badge,
) -> None:
    response = await client.delete(
        f"/api/v1/badges/{deletable_template.id}",
        cookies=auth_cookies,
    )

    assert response.status_code == 204
    assert response.content == b""


@patch("app.services.badge.delete_logo", new_callable=AsyncMock)
async def test_delete_template_removes_from_db(
    _mock_logo: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    deletable_template: Badge,
) -> None:
    id = deletable_template.id

    await client.delete(
        f"/api/v1/badges/{id}",
        cookies=auth_cookies,
    )

    result = await db_session.get(Badge, id)
    assert result is not None
    assert result.deleted_at is not None


@patch("app.services.badge.delete_logo", new_callable=AsyncMock)
async def test_delete_template_triggers_logo_cloudinary_cleanup(
    mock_delete_logo: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    deletable_template: Badge,
) -> None:
    await client.delete(
        f"/api/v1/badges/{deletable_template.id}",
        cookies=auth_cookies,
    )

    mock_delete_logo.assert_awaited_once_with("template-logos/logo-del")


async def test_delete_template_unauthenticated(
    client: AsyncClient,
    deletable_template: Badge,
) -> None:
    response = await client.delete(
        f"/api/v1/badges/{deletable_template.id}",
    )

    assert response.status_code in (401, 403)


async def test_delete_template_not_found(
    client: AsyncClient,
    auth_cookies: dict[str, str],
) -> None:
    response = await client.delete(
        f"/api/v1/badges/{uuid.uuid4()}",
        cookies=auth_cookies,
    )

    assert response.status_code == 404
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "Badge not found."


async def test_delete_template_not_owner(
    client: AsyncClient,
    db_session: AsyncSession,
    platform_template: PlatformTemplate,
) -> None:
    from app.core.security import hash_password
    from app.core.token import create_access_token

    owner = User(
        first_name="Owner",
        last_name="User",
        email="del-owner@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    db_session.add(owner)
    await db_session.flush()

    template = Badge(
        organiser_id=owner.id,
        platform_template_id=platform_template.id,
        title="Owner Event",
        canvas_data={"layout_id": "v1"},
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)

    other = User(
        first_name="Other",
        last_name="User",
        email="del-other@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    response = await client.delete(
        f"/api/v1/badges/{template.id}",
        cookies={settings.ACCESS_COOKIE: create_access_token(other.id)},
    )

    assert response.status_code == 403
    assert response.json()["message"] == "You do not own this badge."


@patch("app.services.badge.delete_logo", new_callable=AsyncMock)
async def test_delete_template_returns_204_despite_cloudinary_failure(
    mock_delete_logo: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    deletable_template: Badge,
) -> None:
    mock_delete_logo.side_effect = Exception("Cloudinary down")

    response = await client.delete(
        f"/api/v1/badges/{deletable_template.id}",
        cookies=auth_cookies,
    )

    assert response.status_code == 204


@patch("app.services.badge.delete_logo", new_callable=AsyncMock)
async def test_delete_template_soft_deleted_returns_404(
    _mock_logo: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    soft_deleted = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Soft Deleted",
        canvas_data={"layout_id": "v1"},
        deleted_at=datetime.now(UTC),
    )
    db_session.add(soft_deleted)
    await db_session.commit()
    await db_session.refresh(soft_deleted)

    response = await client.delete(
        f"/api/v1/badges/{soft_deleted.id}",
        cookies=auth_cookies,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "Badge not found."


@pytest.fixture
async def patch_target(
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> Badge:
    """Template with hashtags used as the target for PATCH tests."""

    template = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Patch Me",
        canvas_data={"layout_id": "v1", "accent": "#000000"},
        default_caption="Original caption",
        destination_link="https://original.example.com",
        thumbnail_url="https://cdn.example.com/original.png",
        access_type=0,
    )
    db_session.add(template)
    await db_session.flush()

    for tag in ["#Before", "#Edit"]:
        db_session.add(BadgeHashtag(badge_id=template.id, hashtag=tag))

    await db_session.commit()
    await db_session.refresh(template)
    return template


async def test_patch_template_returns_200(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    patch_target: Badge,
) -> None:
    response = await client.patch(
        f"/api/v1/badges/{patch_target.id}",
        cookies=auth_cookies,
        json={"title": "Updated Title"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Badge updated successfully."


async def test_patch_template_response_contains_full_object(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    patch_target: Badge,
) -> None:
    response = await client.patch(
        f"/api/v1/badges/{patch_target.id}",
        cookies=auth_cookies,
        json={"title": "Full Response Check"},
    )

    data = response.json()["data"]
    expected_keys = {
        "id",
        "title",
        "platform_template_id",
        "canvas_data",
        "default_caption",
        "destination_link",
        "thumbnail_url",
        "logo_url",
        "access_type",
        "is_published",
        "share_slug",
        "published_at",
        "hashtags",
        "created_at",
        "updated_at",
        "total_shares",
        "total_badges_created",
    }
    assert expected_keys == set(data.keys())


async def test_patch_template_updates_title(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    patch_target: Badge,
) -> None:
    response = await client.patch(
        f"/api/v1/badges/{patch_target.id}",
        cookies=auth_cookies,
        json={"title": "Brand New Title"},
    )

    assert response.json()["data"]["title"] == "Brand New Title"


async def test_patch_template_unset_fields_unchanged(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    patch_target: Badge,
) -> None:
    original_canvas = patch_target.canvas_data

    await client.patch(
        f"/api/v1/badges/{patch_target.id}",
        cookies=auth_cookies,
        json={"title": "Title Only"},
    )

    stored = await db_session.get(Badge, patch_target.id)
    assert stored is not None
    assert stored.canvas_data == original_canvas


async def test_patch_template_replaces_hashtags(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    patch_target: Badge,
) -> None:
    response = await client.patch(
        f"/api/v1/badges/{patch_target.id}",
        cookies=auth_cookies,
        json={"hashtags": ["#NewTag", "#Another"]},
    )

    tags = sorted(response.json()["data"]["hashtags"])
    assert tags == ["#Another", "#NewTag"]


async def test_patch_template_clears_hashtags_with_empty_list(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    patch_target: Badge,
) -> None:
    response = await client.patch(
        f"/api/v1/badges/{patch_target.id}",
        cookies=auth_cookies,
        json={"hashtags": []},
    )

    assert response.json()["data"]["hashtags"] == []


async def test_patch_template_omitting_hashtags_leaves_them_unchanged(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    patch_target: Badge,
) -> None:
    await client.patch(
        f"/api/v1/badges/{patch_target.id}",
        cookies=auth_cookies,
        json={"title": "No Hashtag Key"},
    )

    stored_tags = await db_session.execute(
        select(BadgeHashtag).where(BadgeHashtag.badge_id == patch_target.id)
    )
    tags = sorted(t.hashtag for t in stored_tags.scalars().all())
    assert tags == ["#Before", "#Edit"]


async def test_patch_template_unauthenticated(
    client: AsyncClient,
    patch_target: Badge,
) -> None:
    response = await client.patch(
        f"/api/v1/badges/{patch_target.id}",
        json={"title": "No Auth"},
    )

    assert response.status_code in (401, 403)


async def test_patch_template_not_found(
    client: AsyncClient,
    auth_cookies: dict[str, str],
) -> None:
    response = await client.patch(
        f"/api/v1/badges/{uuid.uuid4()}",
        cookies=auth_cookies,
        json={"title": "Ghost"},
    )

    assert response.status_code == 404
    assert response.json()["message"] == "Badge not found."


async def test_patch_template_not_owner(
    client: AsyncClient,
    db_session: AsyncSession,
    platform_template: PlatformTemplate,
) -> None:
    from app.core.security import hash_password
    from app.core.token import create_access_token

    owner = User(
        first_name="Owner",
        last_name="User",
        email="patch-owner@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    db_session.add(owner)
    await db_session.flush()

    template = Badge(
        organiser_id=owner.id,
        platform_template_id=platform_template.id,
        title="Owned Event",
        canvas_data={"layout_id": "v1"},
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)

    other = User(
        first_name="Other",
        last_name="User",
        email="patch-other@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    response = await client.patch(
        f"/api/v1/badges/{template.id}",
        cookies={settings.ACCESS_COOKIE: create_access_token(other.id)},
        json={"title": "Hijacked"},
    )

    assert response.status_code == 403
    assert response.json()["message"] == "You do not own this badge."


async def test_patch_template_empty_title_rejected(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    patch_target: Badge,
) -> None:
    response = await client.patch(
        f"/api/v1/badges/{patch_target.id}",
        cookies=auth_cookies,
        json={"title": "   "},
    )

    assert response.status_code == 422


async def test_patch_template_empty_body_is_no_op(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    patch_target: Badge,
) -> None:
    """Sending an empty object should succeed and leave all fields unchanged."""
    original_title = patch_target.title

    response = await client.patch(
        f"/api/v1/badges/{patch_target.id}",
        cookies=auth_cookies,
        json={},
    )

    assert response.status_code == 200
    stored = await db_session.get(Badge, patch_target.id)
    assert stored is not None
    assert stored.title == original_title


async def test_patch_template_soft_deleted_returns_404(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    soft_deleted = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Gone",
        canvas_data={"layout_id": "v1"},
        deleted_at=datetime.now(UTC),
    )
    db_session.add(soft_deleted)
    await db_session.commit()
    await db_session.refresh(soft_deleted)

    response = await client.patch(
        f"/api/v1/badges/{soft_deleted.id}",
        cookies=auth_cookies,
        json={"title": "Attempt"},
    )

    assert response.status_code == 404


async def test_analytics_unauthenticated(client: AsyncClient) -> None:
    response = await client.get("/api/v1/badges/analytics")
    assert response.status_code == 401


async def test_analytics_empty_state(
    client: AsyncClient,
    auth_cookies: dict[str, str],
) -> None:
    response = await client.get("/api/v1/badges/analytics", cookies=auth_cookies)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total_organiser_badges"] == 0
    assert data["total_active_badges"] == 0
    assert data["total_draft_badges"] == 0
    assert data["total_shares"] == 0
    assert data["total_badges_created"] == 0
    assert data["platform_template_usage"] == []


async def test_analytics_returns_aggregated_metrics(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    from sqlalchemy import update as sa_update

    b1 = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Published",
        canvas_data={"layout_id": "v1"},
        is_published=True,
        share_slug="published-one",
    )
    b2 = Badge(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Draft",
        canvas_data={"layout_id": "v1"},
    )
    db_session.add_all([b1, b2])
    await db_session.commit()
    await db_session.refresh(b1)
    await db_session.refresh(b2)

    await db_session.execute(
        sa_update(Badge)
        .where(Badge.id == b1.id)
        .values(share_count=20, creation_count=50)
    )
    await db_session.commit()

    response = await client.get("/api/v1/badges/analytics", cookies=auth_cookies)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total_organiser_badges"] == 2
    assert data["total_active_badges"] == 1
    assert data["total_draft_badges"] == 1
    assert data["total_shares"] == 20
    assert data["total_badges_created"] == 50
    assert len(data["platform_template_usage"]) == 1
    assert data["platform_template_usage"][0]["count"] == 2


async def test_analytics_scoped_to_current_user(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    other_user: User,
    platform_template: PlatformTemplate,
) -> None:
    db_session.add(
        Badge(
            organiser_id=test_user.id,
            platform_template_id=platform_template.id,
            title="Mine",
            canvas_data={"layout_id": "v1"},
        )
    )
    db_session.add(
        Badge(
            organiser_id=other_user.id,
            platform_template_id=platform_template.id,
            title="Theirs",
            canvas_data={"layout_id": "v1"},
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/badges/analytics", cookies=auth_cookies)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total_organiser_badges"] == 1
    assert data["total_draft_badges"] == 1


async def test_analytics_total_draft_badges(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    """total_draft_badges == total_organiser_badges - total_active_badges."""
    badges = [
        Badge(
            organiser_id=test_user.id,
            platform_template_id=platform_template.id,
            title=f"Badge {i}",
            canvas_data={"layout_id": "v1"},
            is_published=(i < 2),
            share_slug=f"slug-draft-test-{i}" if i < 2 else None,
        )
        for i in range(5)  # 2 published, 3 draft
    ]
    db_session.add_all(badges)
    await db_session.commit()

    response = await client.get("/api/v1/badges/analytics", cookies=auth_cookies)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total_organiser_badges"] == 5
    assert data["total_active_badges"] == 2
    assert data["total_draft_badges"] == 3


async def test_get_single_badge_success(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    badge: Badge,
) -> None:
    response = await client.get(
        f"/api/v1/badges/{badge.id}",
        cookies=auth_cookies,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Badge retrieved successfully."
    assert data["data"]["id"] == str(badge.id)
    assert data["data"]["title"] == badge.title
    assert data["data"]["is_published"] is False

    expected_keys = {
        "id",
        "title",
        "platform_template_id",
        "canvas_data",
        "default_caption",
        "destination_link",
        "thumbnail_url",
        "logo_url",
        "access_type",
        "is_published",
        "share_slug",
        "published_at",
        "hashtags",
        "created_at",
        "updated_at",
        "total_shares",
        "total_badges_created",
    }
    assert expected_keys == set(data["data"].keys())


async def test_get_single_badge_unauthenticated(
    client: AsyncClient,
    badge: Badge,
) -> None:
    response = await client.get(
        f"/api/v1/badges/{badge.id}",
    )
    assert response.status_code in (401, 403)


async def test_get_single_badge_not_found(
    client: AsyncClient,
    auth_cookies: dict[str, str],
) -> None:
    response = await client.get(
        f"/api/v1/badges/{uuid.uuid4()}",
        cookies=auth_cookies,
    )
    assert response.status_code == 404
    assert response.json()["message"] == "Badge not found."


async def test_get_single_badge_not_owner(
    client: AsyncClient,
    other_auth_cookies: dict[str, str],
    badge: Badge,
) -> None:
    response = await client.get(
        f"/api/v1/badges/{badge.id}",
        cookies=other_auth_cookies,
    )
    assert response.status_code == 403
    assert response.json()["message"] == "You do not own this badge."


async def test_get_single_badge_soft_deleted(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    badge: Badge,
) -> None:
    badge.deleted_at = datetime.now(UTC)
    await db_session.commit()

    response = await client.get(
        f"/api/v1/badges/{badge.id}",
        cookies=auth_cookies,
    )
    assert response.status_code == 404
    assert response.json()["message"] == "Badge not found."
