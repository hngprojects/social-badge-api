import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.core.token import create_access_token
from app.models import Badge, OrganiserTemplate, PlatformTemplate, User


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
        "/api/v1/templates/organizer/instances",
        cookies=auth_cookies,
        json={"platform_template_id": str(platform_template.id)},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Template instance created successfully."
    assert data["data"]["platform_template_id"] == str(platform_template.id)
    assert data["data"]["organiser_id"] == str(test_user.id)
    assert "instance_id" in data["data"]
    assert "created_at" in data["data"]


async def test_create_instance_unauthenticated(
    client: AsyncClient, platform_template: PlatformTemplate
) -> None:
    response = await client.post(
        "/api/v1/templates/organizer/instances",
        json={"platform_template_id": str(platform_template.id)},
    )
    assert response.status_code in (401, 403)


async def test_create_instance_platform_template_not_found(
    client: AsyncClient, auth_cookies: dict[str, str]
) -> None:
    fake_id = uuid.uuid4()
    response = await client.post(
        "/api/v1/templates/organizer/instances",
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
        "/api/v1/templates/organizer/instances",
        cookies=auth_cookies,
        json={},
    )
    assert response.status_code == 422


@pytest.fixture
async def organiser_template(
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> OrganiserTemplate:
    """Seed an organiser template owned by test_user."""
    template = OrganiserTemplate(
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
    organiser_template: OrganiserTemplate,
) -> None:
    response = await client.post(
        f"/api/v1/templates/organizer/{organiser_template.id}/publish",
        cookies=auth_cookies,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Template published successfully."
    assert data["data"]["is_published"] is True
    assert data["data"]["share_slug"] is not None
    assert len(data["data"]["share_slug"]) == 12
    assert data["data"]["published_at"] is not None


async def test_publish_template_unauthenticated(
    client: AsyncClient, organiser_template: OrganiserTemplate
) -> None:
    response = await client.post(
        f"/api/v1/templates/organizer/{organiser_template.id}/publish",
    )
    assert response.status_code in (401, 403)


async def test_publish_template_not_found(
    client: AsyncClient, auth_cookies: dict[str, str]
) -> None:
    fake_id = uuid.uuid4()
    response = await client.post(
        f"/api/v1/templates/organizer/{fake_id}/publish",
        cookies=auth_cookies,
    )
    assert response.status_code == 404
    assert response.json()["message"] == "Template not found."


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

    template = OrganiserTemplate(
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
        f"/api/v1/templates/organizer/{template.id}/publish",
        cookies={settings.ACCESS_COOKIE: other_token},
    )
    assert response.status_code == 403
    assert response.json()["message"] == "You do not own this template."


async def test_publish_template_already_published(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    organiser_template: OrganiserTemplate,
) -> None:
    await client.post(
        f"/api/v1/templates/organizer/{organiser_template.id}/publish",
        cookies=auth_cookies,
    )
    response = await client.post(
        f"/api/v1/templates/organizer/{organiser_template.id}/publish",
        cookies=auth_cookies,
    )
    assert response.status_code == 409
    assert response.json()["message"] == "Template is already published."


async def test_unpublish_template_success(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    organiser_template: OrganiserTemplate,
) -> None:
    publish_response = await client.post(
        f"/api/v1/templates/organizer/{organiser_template.id}/publish",
        cookies=auth_cookies,
    )
    original_slug = publish_response.json()["data"]["share_slug"]

    response = await client.post(
        f"/api/v1/templates/organizer/{organiser_template.id}/unpublish",
        cookies=auth_cookies,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Template unpublished successfully."
    assert data["data"]["is_published"] is False
    assert data["data"]["share_slug"] == original_slug
    assert data["data"]["published_at"] is None


async def test_republish_preserves_slug(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    organiser_template: OrganiserTemplate,
) -> None:
    first = await client.post(
        f"/api/v1/templates/organizer/{organiser_template.id}/publish",
        cookies=auth_cookies,
    )
    original_slug = first.json()["data"]["share_slug"]

    await client.post(
        f"/api/v1/templates/organizer/{organiser_template.id}/unpublish",
        cookies=auth_cookies,
    )
    second = await client.post(
        f"/api/v1/templates/organizer/{organiser_template.id}/publish",
        cookies=auth_cookies,
    )
    assert second.status_code == 200
    assert second.json()["data"]["share_slug"] == original_slug


async def test_unpublish_template_not_found(
    client: AsyncClient, auth_cookies: dict[str, str]
) -> None:
    fake_id = uuid.uuid4()
    response = await client.post(
        f"/api/v1/templates/organizer/{fake_id}/unpublish",
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
) -> OrganiserTemplate:
    """Organiser template instance owned by test_user, no logo yet."""
    instance = OrganiserTemplate(
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
) -> OrganiserTemplate:
    """Organiser template instance that already has an uploaded logo."""
    instance = OrganiserTemplate(
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


@patch("app.services.template.upload_logo", new_callable=AsyncMock)
async def test_upload_logo_success(
    mock_upload: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    template_instance: OrganiserTemplate,
) -> None:
    mock_upload.return_value = (_FAKE_URL, _FAKE_PUBLIC_ID)

    response = await client.put(
        f"/api/v1/templates/organizer/instances/{template_instance.id}/logo",
        cookies=auth_cookies,
        files={"file": ("logo.png", _FAKE_PNG, "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Logo uploaded successfully."
    assert data["data"]["logo_url"] == _FAKE_URL
    mock_upload.assert_called_once_with(_FAKE_PNG)


@patch("app.services.template.delete_logo", new_callable=AsyncMock)
@patch("app.services.template.upload_logo", new_callable=AsyncMock)
async def test_upload_logo_replaces_existing(
    mock_upload: AsyncMock,
    mock_delete: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    template_instance_with_logo: OrganiserTemplate,
) -> None:
    """Uploading a new logo should delete the old Cloudinary asset first."""
    mock_upload.return_value = (_FAKE_URL, _FAKE_PUBLIC_ID)

    response = await client.put(
        f"/api/v1/templates/organizer/instances/{template_instance_with_logo.id}/logo",
        cookies=auth_cookies,
        files={"file": ("logo.jpg", _FAKE_JPEG, "image/jpeg")},
    )

    assert response.status_code == 200
    mock_delete.assert_called_once_with("template-logos/old-logo-id")
    mock_upload.assert_called_once()


@patch("app.services.template.upload_logo", new_callable=AsyncMock)
async def test_upload_logo_unsupported_type(
    mock_upload: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    template_instance: OrganiserTemplate,
) -> None:
    response = await client.put(
        f"/api/v1/templates/organizer/instances/{template_instance.id}/logo",
        cookies=auth_cookies,
        files={"file": ("logo.gif", b"fake-gif-bytes", "image/gif")},
    )

    assert response.status_code == 415
    data = response.json()
    assert data["status"] == "error"
    mock_upload.assert_not_called()


@patch("app.services.template.upload_logo", new_callable=AsyncMock)
async def test_upload_logo_too_large(
    mock_upload: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    template_instance: OrganiserTemplate,
) -> None:
    # PNG magic + enough padding to exceed 2 MB.
    oversized = _FAKE_PNG + b"x" * (2 * 1024 * 1024)

    response = await client.put(
        f"/api/v1/templates/organizer/instances/{template_instance.id}/logo",
        cookies=auth_cookies,
        files={"file": ("logo.png", oversized, "image/png")},
    )

    assert response.status_code == 413
    data = response.json()
    assert data["status"] == "error"
    mock_upload.assert_not_called()


async def test_upload_logo_unauthenticated(
    client: AsyncClient,
    template_instance: OrganiserTemplate,
) -> None:
    response = await client.put(
        f"/api/v1/templates/organizer/instances/{template_instance.id}/logo",
        files={"file": ("logo.png", _FAKE_PNG, "image/png")},
    )

    assert response.status_code in (401, 403)


@patch("app.services.template.upload_logo", new_callable=AsyncMock)
async def test_upload_logo_instance_not_found(
    mock_upload: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
) -> None:
    response = await client.put(
        f"/api/v1/templates/organizer/instances/{uuid.uuid4()}/logo",
        cookies=auth_cookies,
        files={"file": ("logo.png", _FAKE_PNG, "image/png")},
    )

    assert response.status_code == 404
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "Template instance not found."
    mock_upload.assert_not_called()


async def test_upload_logo_forbidden(
    client: AsyncClient,
    other_auth_cookies: dict[str, str],
    template_instance: OrganiserTemplate,
) -> None:
    """A user who does not own the instance should get 403."""
    response = await client.put(
        f"/api/v1/templates/organizer/instances/{template_instance.id}/logo",
        cookies=other_auth_cookies,
        files={"file": ("logo.png", _FAKE_PNG, "image/png")},
    )

    assert response.status_code == 403
    data = response.json()
    assert data["status"] == "error"


@patch("app.services.template.upload_logo", new_callable=AsyncMock)
async def test_upload_logo_rejects_spoofed_mime_type(
    mock_upload: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    template_instance: OrganiserTemplate,
) -> None:
    """File declared as image/png but containing GIF magic bytes should be rejected."""
    gif_bytes = b"GIF89a" + b"\x00" * 20

    response = await client.put(
        f"/api/v1/templates/organizer/instances/{template_instance.id}/logo",
        cookies=auth_cookies,
        files={"file": ("evil.png", gif_bytes, "image/png")},
    )

    assert response.status_code == 415
    mock_upload.assert_not_called()


@patch("app.services.template.upload_logo", new_callable=AsyncMock)
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

    deleted_instance = OrganiserTemplate(
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
        f"/api/v1/templates/organizer/instances/{deleted_instance.id}/logo",
        cookies=auth_cookies,
        files={"file": ("logo.png", _FAKE_PNG, "image/png")},
    )

    assert response.status_code == 404
    mock_upload.assert_not_called()


@patch("app.services.template.delete_logo", new_callable=AsyncMock)
@patch("app.services.template.upload_logo", new_callable=AsyncMock)
async def test_upload_logo_uploads_before_deleting_old(
    mock_upload: AsyncMock,
    mock_delete: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    template_instance_with_logo: OrganiserTemplate,
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
        f"/api/v1/templates/organizer/instances/{template_instance_with_logo.id}/logo",
        cookies=auth_cookies,
        files={"file": ("logo.png", _FAKE_PNG, "image/png")},
    )

    assert response.status_code == 200
    assert call_order == ["upload", "delete"], (
        f"Expected upload before delete, got: {call_order}"
    )


@patch("app.services.template.delete_logo", new_callable=AsyncMock)
@patch("app.services.template.upload_logo", new_callable=AsyncMock)
async def test_upload_logo_rate_limit(
    mock_upload: AsyncMock,
    mock_delete: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    template_instance: OrganiserTemplate,
) -> None:
    mock_upload.return_value = (_FAKE_URL, _FAKE_PUBLIC_ID)

    url = f"/api/v1/templates/organizer/instances/{template_instance.id}/logo"
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
) -> OrganiserTemplate:
    """Seed a published organiser template with a slug, logo, and hashtags."""
    from app.models.templates import TemplateHashtag

    template = OrganiserTemplate(
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
        db_session.add(TemplateHashtag(template_id=template.id, hashtag=tag))

    await db_session.commit()
    await db_session.refresh(template)
    return template


async def test_get_participant_page_success(
    client: AsyncClient,
    published_template: OrganiserTemplate,
) -> None:
    response = await client.get(
        f"/api/v1/templates/organizer/public/{published_template.share_slug}",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Template data retrieved successfully."
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
    template = OrganiserTemplate(
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

    response = await client.get("/api/v1/templates/organizer/public/notags000001")
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
    template = OrganiserTemplate(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Draft Event",
        canvas_data={"layout": "test-v1"},
        is_published=False,
        share_slug="draft0000001",
    )
    db_session.add(template)
    await db_session.commit()

    response = await client.get("/api/v1/templates/organizer/public/draft0000001")
    assert response.status_code == 404
    assert response.json()["message"] == "Template not found."


async def test_get_participant_page_nonexistent_slug(
    client: AsyncClient,
) -> None:
    """A completely random slug should return 404."""
    response = await client.get("/api/v1/templates/organizer/public/doesnotexist1")
    assert response.status_code == 404
    assert response.json()["message"] == "Template not found."


async def test_get_participant_page_soft_deleted(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    """Published but soft-deleted template should return 404."""
    from datetime import UTC, datetime

    template = OrganiserTemplate(
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

    response = await client.get("/api/v1/templates/organizer/public/deleted00001")
    assert response.status_code == 404
    assert response.json()["message"] == "Template not found."


async def test_get_participant_page_no_auth_required(
    client: AsyncClient,
    published_template: OrganiserTemplate,
) -> None:
    """No Bearer token sent — should still return 200, not 401."""
    response = await client.get(
        f"/api/v1/templates/organizer/public/{published_template.share_slug}",
    )
    assert response.status_code == 200


async def test_get_participant_page_was_published_then_unpublished(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    """Slug that was once published but has since been unpublished returns 404."""
    template = OrganiserTemplate(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Past Event",
        canvas_data={"layout": "test-v1"},
        is_published=False,  # was published, now unpublished
        share_slug="waspub000001",  # slug preserved from when it was published
    )
    db_session.add(template)
    await db_session.commit()

    response = await client.get("/api/v1/templates/organizer/public/waspub000001")
    assert response.status_code == 404
    assert response.json()["message"] == "Template not found."


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
) -> OrganiserTemplate:
    """Organiser template with hashtags, used as the duplication source."""
    from app.models.templates import TemplateHashtag

    template = OrganiserTemplate(
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
        db_session.add(TemplateHashtag(template_id=template.id, hashtag=tag))

    await db_session.commit()
    await db_session.refresh(template)
    return template


async def test_duplicate_template_success(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    source_for_duplicate: OrganiserTemplate,
    test_user: User,
) -> None:
    response = await client.post(
        f"/api/v1/templates/organizer/{source_for_duplicate.id}/duplicate",
        cookies=auth_cookies,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Template duplicated successfully."
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
    source_for_duplicate: OrganiserTemplate,
) -> None:
    """The response must never carry a slug or published state."""
    response = await client.post(
        f"/api/v1/templates/organizer/{source_for_duplicate.id}/duplicate",
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
    source_for_duplicate: OrganiserTemplate,
) -> None:
    await client.post(
        f"/api/v1/templates/organizer/{source_for_duplicate.id}/duplicate",
        cookies=auth_cookies,
    )

    await db_session.refresh(source_for_duplicate)
    assert source_for_duplicate.title == "Source Event"


async def test_duplicate_template_unauthenticated(
    client: AsyncClient,
    source_for_duplicate: OrganiserTemplate,
) -> None:
    response = await client.post(
        f"/api/v1/templates/organizer/{source_for_duplicate.id}/duplicate",
    )

    assert response.status_code in (401, 403)


async def test_duplicate_template_not_found(
    client: AsyncClient,
    auth_cookies: dict[str, str],
) -> None:
    response = await client.post(
        f"/api/v1/templates/organizer/{uuid.uuid4()}/duplicate",
        cookies=auth_cookies,
    )

    assert response.status_code == 404
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "Template not found."


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

    template = OrganiserTemplate(
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
        f"/api/v1/templates/organizer/{template.id}/duplicate",
        cookies={settings.ACCESS_COOKIE: other_token},
    )

    assert response.status_code == 403
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "You do not own this template."


async def test_duplicate_soft_deleted_template_returns_404(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    from datetime import UTC, datetime

    deleted = OrganiserTemplate(
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
        f"/api/v1/templates/organizer/{deleted.id}/duplicate",
        cookies=auth_cookies,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "Template not found."


async def test_duplicate_published_template_copy_is_draft(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    from datetime import UTC, datetime

    published = OrganiserTemplate(
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
        f"/api/v1/templates/organizer/{published.id}/duplicate",
        cookies=auth_cookies,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["is_published"] is False


@pytest.fixture
async def organiser_templates_set(
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> list[OrganiserTemplate]:
    """Three templates: two drafts, one published."""
    from datetime import UTC, datetime

    draft_a = OrganiserTemplate(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Draft Alpha",
        canvas_data={"layout_id": "v1"},
        is_published=False,
    )
    draft_b = OrganiserTemplate(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Draft Beta",
        canvas_data={"layout_id": "v1"},
        is_published=False,
    )
    published = OrganiserTemplate(
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
    organiser_templates_set: list[OrganiserTemplate],
) -> None:
    response = await client.get(
        "/api/v1/templates/organizer/instances",
        cookies=auth_cookies,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Template instances retrieved successfully."
    assert data["data"]["total"] == 3
    assert len(data["data"]["templates"]) == 3


async def test_list_instances_response_shape(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    organiser_templates_set: list[OrganiserTemplate],
) -> None:
    response = await client.get(
        "/api/v1/templates/organizer/instances",
        cookies=auth_cookies,
    )

    item = response.json()["data"]["templates"][0]
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
    }
    assert expected_keys == set(item.keys())


async def test_list_instances_status_field_draft(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    organiser_templates_set: list[OrganiserTemplate],
) -> None:
    response = await client.get(
        "/api/v1/templates/organizer/instances",
        cookies=auth_cookies,
    )

    items = response.json()["data"]["templates"]
    draft_items = [t for t in items if not t["is_published"]]
    assert all(t["status"] == "draft" for t in draft_items)


async def test_list_instances_status_field_published(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    organiser_templates_set: list[OrganiserTemplate],
) -> None:
    response = await client.get(
        "/api/v1/templates/organizer/instances",
        cookies=auth_cookies,
    )

    items = response.json()["data"]["templates"]
    published_items = [t for t in items if t["is_published"]]
    assert all(t["status"] == "published" for t in published_items)


async def test_list_instances_canvas_data_not_exposed(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    organiser_templates_set: list[OrganiserTemplate],
) -> None:
    """canvas_data must not appear in the list response — it is large and unused."""
    response = await client.get(
        "/api/v1/templates/organizer/instances",
        cookies=auth_cookies,
    )

    for item in response.json()["data"]["templates"]:
        assert "canvas_data" not in item


async def test_list_instances_empty_when_no_templates(
    client: AsyncClient,
    auth_cookies: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/templates/organizer/instances",
        cookies=auth_cookies,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["templates"] == []
    assert data["total"] == 0
    assert data["prev"] is None
    assert data["next"] is None


async def test_list_instances_unauthenticated(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/templates/organizer/instances")

    assert response.status_code in (401, 403)


async def test_list_instances_excludes_soft_deleted(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    from datetime import UTC, datetime

    live = OrganiserTemplate(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="Live Template",
        canvas_data={"layout_id": "v1"},
    )
    deleted = OrganiserTemplate(
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
        "/api/v1/templates/organizer/instances",
        cookies=auth_cookies,
    )

    data = response.json()["data"]
    assert data["total"] == 1
    assert data["templates"][0]["title"] == "Live Template"


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

    mine = OrganiserTemplate(
        organiser_id=test_user.id,
        platform_template_id=platform_template.id,
        title="My Template",
        canvas_data={"layout_id": "v1"},
    )
    theirs = OrganiserTemplate(
        organiser_id=other.id,
        platform_template_id=platform_template.id,
        title="Their Template",
        canvas_data={"layout_id": "v1"},
    )
    db_session.add(mine)
    db_session.add(theirs)
    await db_session.commit()

    response = await client.get(
        "/api/v1/templates/organizer/instances",
        cookies=auth_cookies,
    )

    data = response.json()["data"]
    assert data["total"] == 1
    assert data["templates"][0]["title"] == "My Template"


async def test_list_instances_pagination_prev_next_links(
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    for i in range(5):
        db_session.add(
            OrganiserTemplate(
                organiser_id=test_user.id,
                platform_template_id=platform_template.id,
                title=f"Event {i}",
                canvas_data={"layout_id": "v1"},
            )
        )
    await db_session.commit()

    response = await client.get(
        "/api/v1/templates/organizer/instances?page=2&limit=2",
        cookies=auth_cookies,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["page"] == 2
    assert data["limit"] == 2
    assert data["total"] == 5
    assert len(data["templates"]) == 2
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
            OrganiserTemplate(
                organiser_id=test_user.id,
                platform_template_id=platform_template.id,
                title=f"Event {i}",
                canvas_data={"layout_id": "v1"},
            )
        )
    await db_session.commit()

    response = await client.get(
        "/api/v1/templates/organizer/instances?page=1&limit=2",
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
            OrganiserTemplate(
                organiser_id=test_user.id,
                platform_template_id=platform_template.id,
                title=f"Event {i}",
                canvas_data={"layout_id": "v1"},
            )
        )
    await db_session.commit()

    response = await client.get(
        "/api/v1/templates/organizer/instances?page=2&limit=2",
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
        "/api/v1/templates/organizer/instances?page=0",
        cookies=auth_cookies,
    )

    assert response.status_code == 422


async def test_list_instances_limit_exceeds_maximum(
    client: AsyncClient,
    auth_cookies: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/templates/organizer/instances?limit=101",
        cookies=auth_cookies,
    )

    assert response.status_code == 422


@pytest.fixture
async def deletable_template(
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> OrganiserTemplate:
    template = OrganiserTemplate(
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

    db_session.add(
        Badge(
            template_id=template.id,
            participant_name="Attendee",
            badge_image_url=(
                "https://res.cloudinary.com/mycloud/image/upload/badges/badge-del.png"
            ),
            badge_public_id="badges/badge-del",
        )
    )

    await db_session.commit()
    await db_session.refresh(template)
    return template


@patch("app.services.template.delete_asset", new_callable=AsyncMock)
@patch("app.services.template.delete_logo", new_callable=AsyncMock)
async def test_delete_template_returns_204(
    _mock_logo: AsyncMock,
    _mock_asset: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    deletable_template: OrganiserTemplate,
) -> None:
    response = await client.delete(
        f"/api/v1/templates/organizer/{deletable_template.id}",
        cookies=auth_cookies,
    )

    assert response.status_code == 204
    assert response.content == b""


@patch("app.services.template.delete_asset", new_callable=AsyncMock)
@patch("app.services.template.delete_logo", new_callable=AsyncMock)
async def test_delete_template_removes_from_db(
    _mock_logo: AsyncMock,
    _mock_asset: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    deletable_template: OrganiserTemplate,
) -> None:
    template_id = deletable_template.id

    await client.delete(
        f"/api/v1/templates/organizer/{template_id}",
        cookies=auth_cookies,
    )

    result = await db_session.get(OrganiserTemplate, template_id)
    assert result is None


@patch("app.services.template.delete_asset", new_callable=AsyncMock)
@patch("app.services.template.delete_logo", new_callable=AsyncMock)
async def test_delete_template_triggers_logo_cloudinary_cleanup(
    mock_delete_logo: AsyncMock,
    mock_delete_asset: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    deletable_template: OrganiserTemplate,
) -> None:
    await client.delete(
        f"/api/v1/templates/organizer/{deletable_template.id}",
        cookies=auth_cookies,
    )

    mock_delete_logo.assert_awaited_once_with("template-logos/logo-del")


@patch("app.services.template.delete_asset", new_callable=AsyncMock)
@patch("app.services.template.delete_logo", new_callable=AsyncMock)
async def test_delete_template_triggers_badge_cloudinary_cleanup(
    mock_delete_logo: AsyncMock,
    mock_delete_asset: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    deletable_template: OrganiserTemplate,
) -> None:
    await client.delete(
        f"/api/v1/templates/organizer/{deletable_template.id}",
        cookies=auth_cookies,
    )

    mock_delete_asset.assert_awaited_once_with("badges/badge-del")


async def test_delete_template_unauthenticated(
    client: AsyncClient,
    deletable_template: OrganiserTemplate,
) -> None:
    response = await client.delete(
        f"/api/v1/templates/organizer/{deletable_template.id}",
    )

    assert response.status_code in (401, 403)


async def test_delete_template_not_found(
    client: AsyncClient,
    auth_cookies: dict[str, str],
) -> None:
    response = await client.delete(
        f"/api/v1/templates/organizer/{uuid.uuid4()}",
        cookies=auth_cookies,
    )

    assert response.status_code == 404
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "Template not found."


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

    template = OrganiserTemplate(
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
        f"/api/v1/templates/organizer/{template.id}",
        cookies={settings.ACCESS_COOKIE: create_access_token(other.id)},
    )

    assert response.status_code == 403
    assert response.json()["message"] == "You do not own this template."


@patch("app.services.template.delete_asset", new_callable=AsyncMock)
@patch("app.services.template.delete_logo", new_callable=AsyncMock)
async def test_delete_template_returns_204_despite_cloudinary_failure(
    mock_delete_logo: AsyncMock,
    mock_delete_asset: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    deletable_template: OrganiserTemplate,
) -> None:
    mock_delete_logo.side_effect = Exception("Cloudinary down")
    mock_delete_asset.side_effect = Exception("Cloudinary down")

    response = await client.delete(
        f"/api/v1/templates/organizer/{deletable_template.id}",
        cookies=auth_cookies,
    )

    assert response.status_code == 204


@patch("app.services.template.delete_asset", new_callable=AsyncMock)
@patch("app.services.template.delete_logo", new_callable=AsyncMock)
async def test_delete_template_soft_deleted_returns_404(
    _mock_logo: AsyncMock,
    _mock_asset: AsyncMock,
    client: AsyncClient,
    auth_cookies: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    platform_template: PlatformTemplate,
) -> None:
    soft_deleted = OrganiserTemplate(
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
        f"/api/v1/templates/organizer/{soft_deleted.id}",
        cookies=auth_cookies,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "Template not found."
