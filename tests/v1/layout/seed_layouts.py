"""Tests for GET /api/v1/layouts endpoint."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.dependencies import get_current_user
from app.db.session import get_session
from app.models.templates import PlatformTemplate
from app.models.users import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="testuser@example.com",
        first_name="Test",
        last_name="User",
        is_verified=True,
    )


def _make_template(**kwargs) -> PlatformTemplate:
    defaults = dict(
        id=uuid.uuid4(),
        title="Classic",
        name="Classic",
        description="A clean minimal badge.",
        thumbnail_url="https://placehold.co/400x200?text=Classic",
        canvas_data={"background": "#fff"},
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    defaults.update(kwargs)
    return PlatformTemplate(**defaults)


def _mock_session(mock_session: AsyncMock, templates: list, total: int | None = None) -> None:
    total = total if total is not None else len(templates)
    mock_session.scalar = AsyncMock(return_value=total)
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = templates
    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value = mock_scalars
    mock_session.execute = AsyncMock(return_value=mock_execute_result)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def auth_override():
    app.dependency_overrides[get_current_user] = lambda: _make_user()
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def session_override(mock_session):
    app.dependency_overrides[get_session] = lambda: mock_session
    yield mock_session
    app.dependency_overrides.pop(get_session, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_layouts_success(session_override, auth_override):
    """Authenticated request returns 200 with paginated layouts."""
    templates = [
        _make_template(name="Classic", description="Clean and minimal."),
        _make_template(name="Bold Dark", description="High contrast dark theme."),
    ]
    _mock_session(session_override, templates)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/layouts")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["status"] == "success"
    assert body["message"] == "Layouts retrieved successfully"
    data = body["data"]
    assert data["page"] == 1
    assert data["limit"] == 10
    assert data["total"] == 2
    assert len(data["layouts"]) == 2


@pytest.mark.asyncio
async def test_get_layouts_unauthenticated(session_override):
    """Request without auth returns 401 or 403."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/layouts")

    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    )


@pytest.mark.asyncio
async def test_get_layouts_empty(session_override, auth_override):
    """Returns empty list when no active templates exist."""
    _mock_session(session_override, [], total=0)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/layouts")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["data"]
    assert data["total"] == 0
    assert data["layouts"] == []


@pytest.mark.asyncio
async def test_get_layouts_pagination(session_override, auth_override):
    """page and limit query params are forwarded correctly."""
    templates = [_make_template(name=f"Template {i}", description=f"Desc {i}") for i in range(3)]
    _mock_session(session_override, templates, total=20)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/layouts", params={"page": 2, "limit": 3})

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["data"]
    assert data["page"] == 2
    assert data["limit"] == 3
    assert data["total"] == 20
    assert len(data["layouts"]) == 3


@pytest.mark.asyncio
async def test_get_layouts_response_shape(session_override, auth_override):
    """Each layout item contains all four required fields."""
    template = _make_template(
        name="Gradient",
        description="Smooth gradient background.",
        thumbnail_url="https://placehold.co/400x200?text=Gradient",
    )
    _mock_session(session_override, [template])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/layouts")

    layout = response.json()["data"]["layouts"][0]
    assert "layout_id" in layout
    assert "name" in layout
    assert "description" in layout
    assert "thumbnail_url" in layout
    assert layout["name"] == "Gradient"
    assert layout["description"] == "Smooth gradient background."
    assert layout["thumbnail_url"] == "https://placehold.co/400x200?text=Gradient"


@pytest.mark.asyncio
async def test_get_layouts_defaults(session_override, auth_override):
    """Default page=1 and limit=10 when not supplied."""
    _mock_session(session_override, [], total=0)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/layouts")

    data = response.json()["data"]
    assert data["page"] == 1
    assert data["limit"] == 10