"""Pydantic schemas for admin platform template operations."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_VALID_TEMPLATE_CATEGORIES: frozenset[str] = frozenset(
    {
        "festivals",
        "hackathons",
        "conferences",
        "community",
        "bootcamp",
        "meetups",
        "speakers",
        "trending",
        "general",
        "event",
        "updated event",
    }
)


class CreatePlatformTemplateRequest(BaseModel):
    """Payload for creating a platform template."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Reddit Summit Badge",
                "category": "Event",
                "canvas_data": {
                    "layout_id": "photo_gradient_v1",
                    "background": {
                        "type": "gradient",
                        "gradient": {
                            "colors": ["#FF6B6B", "#FF8E53"],
                            "direction": "135deg",
                        },
                    },
                    "typography": {
                        "font_family": "DM Sans",
                        "size_px": 42,
                        "weight": "bold",
                        "italic": False,
                        "underline": False,
                    },
                    "logo": {
                        "url": "https://res.cloudinary.com/...",
                        "public_id": "badges/logos/abc123",
                        "position": "top-center",
                    },
                    "fields": [
                        {
                            "key": "event_date",
                            "type": "static",
                            "label": "Event Date",
                            "value": "JULY 21ST",
                            "visible": True,
                        },
                        {
                            "key": "event_name",
                            "type": "static",
                            "label": "Event Name",
                            "value": "REDDIT SUMMIT",
                            "visible": True,
                        },
                        {
                            "key": "participant_name",
                            "type": "participant_input",
                            "label": "NAME",
                            "placeholder": "Nickname",
                            "required": True,
                            "visible": True,
                        },
                        {
                            "key": "participant_photo",
                            "type": "participant_upload",
                            "label": "YOUR PHOTO",
                            "required": False,
                            "accepted_formats": ["jpg", "png", "webp"],
                            "max_size_mb": 5,
                            "visible": True,
                        },
                    ],
                    "output": {"width_px": 1080, "height_px": 1350, "format": "png"},
                },
                "thumbnail_url": "https://res.cloudinary.com/...",
                "is_active": True,
            }
        }
    )

    title: str = Field(..., max_length=200)
    category: str = Field(..., max_length=50)
    canvas_data: dict[str, Any] | None = None
    thumbnail_url: str | None = None
    is_active: bool = True

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v.lower() not in _VALID_TEMPLATE_CATEGORIES:
            raise ValueError(
                f"Invalid category '{v}'. Valid options: "
                + ", ".join(sorted(_VALID_TEMPLATE_CATEGORIES))
            )
        return v


class UpdatePlatformTemplateRequest(BaseModel):
    """Payload for updating a platform template."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Updated Reddit Summit Badge",
                "category": "Event",
                "canvas_data": {
                    "layout_id": "photo_gradient_v1",
                    "background": {
                        "type": "gradient",
                        "gradient": {
                            "colors": ["#FF6B6B", "#FF8E53"],
                            "direction": "135deg",
                        },
                    },
                    "typography": {
                        "font_family": "DM Sans",
                        "size_px": 42,
                        "weight": "bold",
                        "italic": False,
                        "underline": False,
                    },
                    "logo": {
                        "url": "https://res.cloudinary.com/...",
                        "public_id": "badges/logos/abc123",
                        "position": "top-center",
                    },
                    "fields": [
                        {
                            "key": "event_date",
                            "type": "static",
                            "label": "Event Date",
                            "value": "JULY 21ST",
                            "visible": True,
                        },
                        {
                            "key": "event_name",
                            "type": "static",
                            "label": "Event Name",
                            "value": "REDDIT SUMMIT",
                            "visible": True,
                        },
                        {
                            "key": "participant_name",
                            "type": "participant_input",
                            "label": "NAME",
                            "placeholder": "Nickname",
                            "required": True,
                            "visible": True,
                        },
                        {
                            "key": "participant_photo",
                            "type": "participant_upload",
                            "label": "YOUR PHOTO",
                            "required": False,
                            "accepted_formats": ["jpg", "png", "webp"],
                            "max_size_mb": 5,
                            "visible": True,
                        },
                    ],
                    "output": {"width_px": 1080, "height_px": 1350, "format": "png"},
                },
                "thumbnail_url": "https://res.cloudinary.com/...",
                "is_active": False,
            }
        }
    )

    title: str | None = Field(None, max_length=200)
    category: str | None = Field(None, max_length=50)
    canvas_data: dict[str, Any] | None = None
    thumbnail_url: str | None = None
    is_active: bool | None = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str | None) -> str | None:
        if v is not None and v.lower() not in _VALID_TEMPLATE_CATEGORIES:
            raise ValueError(
                f"Invalid category '{v}'. Valid options: "
                + ", ".join(sorted(_VALID_TEMPLATE_CATEGORIES))
            )
        return v


class PlatformTemplateResponse(BaseModel):
    """Response schema for platform template data."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    category: str
    canvas_data: dict[str, Any] | None
    thumbnail_url: str | None
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None
