from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlatformTemplateResponse(BaseModel):
    """Data transfer object representing a platform-wide badge template, describing its
    gallery card layout, visual style options, and usage statistics."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Unique identifier for the platform template.")
    title: str = Field(..., description="Display name shown on the gallery card.")
    category: str | None = Field(
        None,
        description=(
            "Gallery filter category. One of: festivals, hackathons, conferences, "
            "community, bootcamp, meetups, speakers, trending."
        ),
    )
    thumbnail_url: str | None = Field(
        None,
        description="Preview image URL shown on the gallery card.",
    )
    canvas_data: dict[str, Any] | None = Field(
        None,
        description=(
            "Full layout descriptor. The organiser editor reads background.options "
            "to render the colour/gradient swatches and fields[] to build the "
            "customisation form."
        ),
    )
    is_active: bool = Field(
        ..., description="False means the template is hidden from the gallery."
    )
    total_badges_made: int = Field(
        ..., description="Total badges created from this template (platform-wide)."
    )
    created_at: datetime | None = Field(
        None, description="When the template was created."
    )


class PlatformTemplateListResponse(BaseModel):
    """Data transfer object representing a paginated collection of platform templates,
    complete with pagination metadata and cursor links."""

    templates: list[PlatformTemplateResponse]
    total: int = Field(
        ..., description="Total number of templates matching the filter."
    )
    page: int = Field(..., description="Current page number.")
    limit: int = Field(..., description="Items per page.")
    prev: str | None = Field(
        default=None, description="Relative URL to the previous page."
    )
    next: str | None = Field(default=None, description="Relative URL to the next page.")
