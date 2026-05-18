import pytest
from pydantic import ValidationError

from app.schemas.admin import (
    CreatePlatformTemplateRequest,
    PlatformTemplateResponse,
    UpdatePlatformTemplateRequest,
)


def test_create_platform_template_request_valid() -> None:
    payload = {
        "title": "Conference Template",
        "category": "Event",
        "canvas_data": {"layout": "conf-v1"},
        "thumbnail_url": "https://example.com/conf.png",
        "is_active": False,
    }
    req = CreatePlatformTemplateRequest(**payload)

    assert req.title == payload["title"]
    assert req.category == payload["category"]
    assert req.canvas_data == payload["canvas_data"]
    assert req.thumbnail_url == payload["thumbnail_url"]
    assert req.is_active is False


def test_create_platform_template_request_missing_title() -> None:
    with pytest.raises(ValidationError):
        CreatePlatformTemplateRequest.model_validate(
            {
                "category": "Event",
                "canvas_data": {"layout": "conf-v1"},
                "thumbnail_url": None,
                "is_active": True,
            }
        )


def test_create_platform_template_request_title_too_long() -> None:
    with pytest.raises(ValidationError):
        CreatePlatformTemplateRequest(
            title="x" * 201,
            category="Event",
            canvas_data=None,
            thumbnail_url=None,
            is_active=True,
        )


def test_update_platform_template_request_all_optional() -> None:
    req = UpdatePlatformTemplateRequest()
    assert req.title is None
    assert req.category is None
    assert req.canvas_data is None
    assert req.thumbnail_url is None
    assert req.is_active is None


def test_update_platform_template_request_title_too_long() -> None:
    with pytest.raises(ValidationError):
        UpdatePlatformTemplateRequest(title="x" * 201)


def test_platform_template_response_valid() -> None:
    payload = {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "title": "Response Template",
        "category": "Education",
        "canvas_data": {"layout": "v1"},
        "thumbnail_url": None,
        "is_active": True,
        "created_at": None,
        "updated_at": None,
    }
    resp = PlatformTemplateResponse(**payload)

    assert str(resp.id) == payload["id"]
    assert resp.title == "Response Template"
    assert resp.category == "Education"
    assert resp.canvas_data == {"layout": "v1"}
    assert resp.thumbnail_url is None
    assert resp.is_active is True
