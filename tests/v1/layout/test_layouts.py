# ruff: noqa: I001
"""Tests for the GET /api/v1/layouts endpoint."""

from pathlib import Path
import sys
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from app.db.session import get_session
from app.dependencies import get_current_user
from app.main import app
from app.models.templates import PlatformTemplate
from app.models.users import User


API_PATH = "/api/v1/layouts"


def _make_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="testuser@example.com",
        first_name="Test",
        last_name="User",
        is_email_verified=True,
    )


def _make_template(**kwargs) -> PlatformTemplate:
    defaults = {
        "id": uuid.uuid4(),
        "title": "Classic",
        "description": "A clean minimal badge layout.",
        "thumbnail_url": "https://placehold.co/400x200?text=Classic",
        "canvas_data": {"background": "#fff"},
        "is_active": True,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(kwargs)
    return PlatformTemplate(**defaults)


def _mock_layout_query(
    mock_session: AsyncMock,
    templates: list[PlatformTemplate],
    total: int | None = None,
) -> None:
    query_total = len(templates) if total is None else total
    mock_session.scalar = AsyncMock(return_value=query_total)

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = templates

    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value = mock_scalars
    mock_session.execute = AsyncMock(return_value=mock_execute_result)


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def auth_override():
    app.dependency_overrides[get_current_user] = _make_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def session_override(mock_session: AsyncMock) -> AsyncMock:
    app.dependency_overrides[get_session] = lambda: mock_session
    yield mock_session
    app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_get_layouts_success(session_override: AsyncMock, auth_override) -> None:
    templates = [
        _make_template(title="Classic", description="Clean and minimal."),
        _make_template(title="Bold Dark", description="High contrast dark theme."),
    ]
    _mock_layout_query(session_override, templates)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(API_PATH)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["status"] == "success"
    assert body["message"] == "Layouts retrieved successfully"
    assert body["data"] == {
        "page": 1,
        "limit": 10,
        "total": 2,
        "layouts": [
            {
                "layout_id": str(templates[0].id),
                "name": "Classic",
                "description": "Clean and minimal.",
                "thumbnail_url": "https://placehold.co/400x200?text=Classic",
            },
            {
                "layout_id": str(templates[1].id),
                "name": "Bold Dark",
                "description": "High contrast dark theme.",
                "thumbnail_url": "https://placehold.co/400x200?text=Classic",
            },
        ],
    }
    session_override.scalar.assert_awaited_once()
    session_override.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_layouts_requires_authentication(session_override: AsyncMock) -> None:
    _mock_layout_query(session_override, [])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(API_PATH)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    session_override.scalar.assert_not_awaited()
    session_override.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_layouts_empty(session_override: AsyncMock, auth_override) -> None:
    _mock_layout_query(session_override, [], total=0)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(API_PATH)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"] == {
        "page": 1,
        "limit": 10,
        "total": 0,
        "layouts": [],
    }


@pytest.mark.asyncio
async def test_get_layouts_paginates(
    session_override: AsyncMock,
    auth_override,
) -> None:
    templates = [
        _make_template(title=f"Template {index}", description=f"Desc {index}")
        for index in range(3)
    ]
    _mock_layout_query(session_override, templates, total=20)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(API_PATH, params={"page": 2, "limit": 3})

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["data"]
    assert data["page"] == 2
    assert data["limit"] == 3
    assert data["total"] == 20
    assert [layout["name"] for layout in data["layouts"]] == [
        "Template 0",
        "Template 1",
        "Template 2",
    ]


@pytest.mark.asyncio
async def test_get_layouts_allows_null_thumbnail(
    session_override: AsyncMock,
    auth_override,
) -> None:
    template = _make_template(
        title="No Preview",
        description="Layout without a thumbnail.",
        thumbnail_url=None,
    )
    _mock_layout_query(session_override, [template])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(API_PATH)

    assert response.status_code == status.HTTP_200_OK
    layout = response.json()["data"]["layouts"][0]
    assert layout == {
        "layout_id": str(template.id),
        "name": "No Preview",
        "description": "Layout without a thumbnail.",
        "thumbnail_url": None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"limit": 0},
        {"limit": 101},
    ],
)
async def test_get_layouts_validates_pagination_params(
    session_override: AsyncMock,
    auth_override,
    params: dict[str, int],
) -> None:
    _mock_layout_query(session_override, [])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(API_PATH, params=params)

    assert response.status_code == 422
    session_override.scalar.assert_not_awaited()
    session_override.execute.assert_not_awaited()
