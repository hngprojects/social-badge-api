import uuid

from pydantic import BaseModel, Field


class LayoutResponse(BaseModel):
    layout_id: uuid.UUID

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable layout name",
    )

    description: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="Short description shown in UI",
    )

    thumbnail_url: str | None = Field(
        None,
        description="Public preview image",
    )


class PaginatedLayouts(BaseModel):
    page: int
    limit: int
    total: int
    layouts: list[LayoutResponse]
