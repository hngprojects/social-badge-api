import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.core.token import create_access_token
from app.models import PlatformTemplate, Role, User, UserRole
from app.models import PlatformTemplate


@pytest.fixture
async def platform_template(db_session: AsyncSession) -> PlatformTemplate:
    template = PlatformTemplate(
        title="Admin Layout",
        category="General",
        canvas_data={"layout": "admin-v1"},
        thumbnail_url="https://example.com/thumb.png",
        is_active=True,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        first_name="Admin",
        last_name="User",
        email="admin@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def admin_role(db_session: AsyncSession) -> Role:
    role = Role(name="admin")
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)
    return role


@pytest.fixture
async def admin_user_role(
    db_session: AsyncSession, admin_user: User, admin_role: Role
) -> UserRole:
    user_role = UserRole(user_id=admin_user.id, role_id=admin_role.id)
    db_session.add(user_role)
    await db_session.commit()
    await db_session.refresh(user_role)
    return user_role


@pytest.fixture
def admin_auth_cookies(admin_user: User, admin_user_role: UserRole) -> dict[str, str]:
    token = create_access_token(admin_user.id)
    return {settings.ACCESS_COOKIE: token}


@pytest.fixture
async def non_admin_user(db_session: AsyncSession) -> User:
    user = User(
        first_name="Non",
        last_name="Admin",
        email="nonadmin@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def non_admin_auth_cookies(non_admin_user: User) -> dict[str, str]:
    token = create_access_token(non_admin_user.id)
    return {settings.ACCESS_COOKIE: token}


async def test_create_platform_template_success(
    client: AsyncClient, admin_auth_cookies: dict[str, str]
) -> None:
async def test_create_platform_template_success(client: AsyncClient) -> None:
    payload = {
        "title": "Conference Template",
        "category": "Event",
        "canvas_data": {"layout": "conf-v1"},
        "thumbnail_url": "https://example.com/conf.png",
        "is_active": False,
    }
    response = await client.post(
        "/api/v1/admin/platform-templates",
        json=payload,
        cookies=admin_auth_cookies,
    )
    response = await client.post("/api/v1/admin/platform-templates", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Platform template created successfully."
    assert data["data"]["title"] == payload["title"]
    assert data["data"]["category"] == payload["category"]
    assert data["data"]["canvas_data"] == payload["canvas_data"]
    assert data["data"]["thumbnail_url"] == payload["thumbnail_url"]
    assert data["data"]["is_active"] is False
    assert data["data"]["id"] is not None
    assert data["data"]["created_at"] is not None


async def test_create_platform_template_validation_error(
    client: AsyncClient, admin_auth_cookies: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/admin/platform-templates",
        json={},
        cookies=admin_auth_cookies,
    )
    client: AsyncClient,
) -> None:
    response = await client.post("/api/v1/admin/platform-templates", json={})

    assert response.status_code == 422
    data = response.json()
    assert data["status"] == "error"


async def test_update_platform_template_success(
    client: AsyncClient,
    platform_template: PlatformTemplate,
    admin_auth_cookies: dict[str, str],
    client: AsyncClient, platform_template: PlatformTemplate
) -> None:
    payload = {
        "title": "Updated Template",
        "category": "Updated Event",
        "canvas_data": {"layout": "updated"},
        "thumbnail_url": "https://example.com/updated.png",
        "is_active": False,
    }
    response = await client.patch(
        f"/api/v1/admin/platform-templates/{platform_template.id}",
        json=payload,
        cookies=admin_auth_cookies,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Platform template updated successfully."
    assert data["data"]["title"] == payload["title"]
    assert data["data"]["category"] == payload["category"]
    assert data["data"]["canvas_data"] == payload["canvas_data"]
    assert data["data"]["thumbnail_url"] == payload["thumbnail_url"]
    assert data["data"]["is_active"] is False


async def test_update_platform_template_not_found(
    client: AsyncClient, admin_auth_cookies: dict[str, str]
) -> None:
    response = await client.patch(
        f"/api/v1/admin/platform-templates/{uuid.uuid4()}",
        json={"title": "Updated"},
        cookies=admin_auth_cookies,
async def test_update_platform_template_not_found(client: AsyncClient) -> None:
    response = await client.patch(
        f"/api/v1/admin/platform-templates/{uuid.uuid4()}",
        json={"title": "Updated"},
    )

    assert response.status_code == 404
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "Platform template not found."


async def test_delete_platform_template_success(
    client: AsyncClient,
    db_session: AsyncSession,
    platform_template: PlatformTemplate,
    admin_auth_cookies: dict[str, str],
) -> None:
    response = await client.delete(
        f"/api/v1/admin/platform-templates/{platform_template.id}",
        cookies=admin_auth_cookies,
) -> None:
    response = await client.delete(
        f"/api/v1/admin/platform-templates/{platform_template.id}"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Platform template deleted successfully."
    assert data["data"] is None

    deleted = await db_session.get(PlatformTemplate, platform_template.id)
    assert deleted is None


async def test_delete_platform_template_not_found(
    client: AsyncClient, admin_auth_cookies: dict[str, str]
) -> None:
    response = await client.delete(
        f"/api/v1/admin/platform-templates/{uuid.uuid4()}",
        cookies=admin_auth_cookies,
    )
async def test_delete_platform_template_not_found(client: AsyncClient) -> None:
    response = await client.delete(f"/api/v1/admin/platform-templates/{uuid.uuid4()}")

    assert response.status_code == 404
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "Platform template not found."


async def test_create_platform_template_forbidden_for_non_admin(
    client: AsyncClient, non_admin_auth_cookies: dict[str, str]
) -> None:
    payload = {
        "title": "Conference Template",
        "category": "Event",
        "canvas_data": {"layout": "conf-v1"},
        "thumbnail_url": "https://example.com/conf.png",
        "is_active": False,
    }
    response = await client.post(
        "/api/v1/admin/platform-templates",
        json=payload,
        cookies=non_admin_auth_cookies,
    )

    assert response.status_code == 403
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "Admin access required"
