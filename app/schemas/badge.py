from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
)


class CreateBadgeRequest(BaseModel):
    platform_template_id: UUID = Field(
        ...,
        description="The id of the platform template the organiser is starting from.",
        json_schema_extra={"example": "019e1b66-c4ec-7b80-8c85-84c2fe4f9c84"},
    )


class CreateBadgeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="The id of the new organiser template instance.",
    )
    platform_template_id: UUID = Field(
        ...,
        description="The id of the platform template the instance is based on.",
    )
    organiser_id: UUID = Field(
        ...,
        description="The id of the organiser who owns this instance.",
    )
    created_at: datetime = Field(
        ...,
        description="When the instance was created.",
    )


class PublishedBadgeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="The template instance id.")
    title: str = Field(..., description="The template title.")
    is_published: bool = Field(..., description="Whether the template is published.")
    published_at: datetime | None = Field(
        ..., description="When the template was published (null if never published)."
    )
    share_slug: str | None = Field(
        ..., description="The public share slug (null if never published)."
    )
    updated_at: datetime | None = Field(
        ..., description="When the template was last updated."
    )


class LogoUploadResponse(BaseModel):
    logo_url: str = Field(
        ...,
        description="The Cloudinary URL of the uploaded logo.",
        json_schema_extra={
            "example": "https://res.cloudinary.com/demo/image/upload/template-logos/abc123.png"
        },
    )


class PublicBadgePageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str = Field(..., description="The event/template title.")
    canvas_data: dict[str, Any] = Field(
        ..., description="Layout and branding JSON for live badge preview."
    )
    logo_url: str | None = Field(
        None, description="URL of the organiser's uploaded logo."
    )
    default_caption: str | None = Field(
        None, description="Pre-filled share caption set by the organiser."
    )
    destination_link: str | None = Field(
        None, description="Destination link set by the organiser."
    )
    hashtags: list[str] = Field(
        default_factory=list,
        description="Hashtags associated with the template.",
    )


class DuplicateBadgeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="ID of the new draft template copy.")
    title: str = Field(..., description="Title of the template copy.")
    platform_template_id: UUID = Field(
        ..., description="Platform template the copy is based on."
    )
    organiser_id: UUID = Field(..., description="Owner of the copy.")
    is_published: bool = Field(..., description="Always False for a new copy.")
    created_at: datetime = Field(..., description="When the copy was created.")


class BadgeSummary(BaseModel):
    """Per-item shape for the organiser's template dashboard list.

    canvas_data is intentionally excluded — it is large and not needed
    for rendering a dashboard card.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID = Field(..., description="Unique identifier for the template instance.")
    title: str = Field(..., description="Template title set by the organiser.")
    platform_template_id: UUID = Field(
        ..., description="The platform template this instance is based on."
    )
    thumbnail_url: str | None = Field(
        None, description="Preview image URL for the dashboard card."
    )
    is_published: bool = Field(
        ..., description="Whether the template is currently published."
    )
    share_slug: str | None = Field(
        None,
        description="Public share slug, present once the template has been published.",
    )
    published_at: datetime | None = Field(
        None, description="When the template was last published."
    )
    created_at: datetime | None = Field(
        None, description="When the template instance was created."
    )
    updated_at: datetime | None = Field(
        None, description="When the template was last modified."
    )
    total_shares: int = Field(
        ...,
        validation_alias="share_count",
        description="Total shares for this badge.",
    )
    total_badges_created: int = Field(
        ...,
        validation_alias="creation_count",
        description="Total badges created from the public page.",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> str:
        return "published" if self.is_published else "draft"


class BadgeListResponse(BaseModel):
    badges: list[BadgeSummary]
    total: int = Field(..., description="Total badges matching the filter.")
    page: int = Field(..., description="Current page number.")
    limit: int = Field(..., description="Items per page.")
    prev: str | None = Field(None, description="Relative URL to the previous page.")
    next: str | None = Field(None, description="Relative URL to the next page.")


class EditBadgeRequest(BaseModel):
    title: str | None = None
    canvas_data: dict[str, Any] | None = None
    default_caption: str | None = None
    destination_link: str | None = None
    thumbnail_url: str | None = None
    access_type: int | None = None
    hashtags: list[str] | None = None

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, val: str | None) -> str | None:
        if val is not None and not val.strip():
            raise ValueError("title cannot be empty")
        return val.strip() if val is not None else val

    @field_validator("hashtags")
    @classmethod
    def clean_hashtags(cls, val: list[str] | None) -> list[str] | None:
        if val is None:
            return None
        stripped = [tag.strip() for tag in val if tag.strip()]
        # Preserve insertion order while deduplicating.
        return list(dict.fromkeys(stripped))


class BadgeDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    title: str
    platform_template_id: UUID
    canvas_data: dict[str, Any]
    default_caption: str | None
    destination_link: str | None
    thumbnail_url: str | None
    logo_url: str | None
    access_type: int
    is_published: bool
    share_slug: str | None
    published_at: datetime | None
    hashtags: list[str]
    created_at: datetime | None
    updated_at: datetime | None
    total_shares: int = Field(validation_alias="share_count")
    total_badges_created: int = Field(validation_alias="creation_count")

    @field_validator("hashtags", mode="before")
    @classmethod
    def extract_hashtag_values(cls, val: Any) -> list[str]:
        """Convert a list of BadgeHashtag ORM objects to plain strings."""
        if not isinstance(val, list):
            return []
        return [item.hashtag if hasattr(item, "hashtag") else str(item) for item in val]


class PlatformTemplateUsage(BaseModel):
    platform_template_id: UUID = Field(
        ..., description="The platform template the badges are based on."
    )
    count: int = Field(..., description="Number of badges using this template.")


class BadgeAnalyticsResponse(BaseModel):
    total_organiser_badges: int = Field(
        ...,
        description="Total badges owned by the organiser (excluding soft-deleted).",
    )
    total_active_badges: int = Field(
        ..., description="Count of currently published badges."
    )
    total_shares: int = Field(
        ..., description="Sum of share_count across all the organiser's badges."
    )
    total_badges_created: int = Field(
        ..., description="Sum of creation_count across all the organiser's badges."
    )
    platform_template_usage: list[PlatformTemplateUsage] = Field(
        default_factory=list,
        description=(
            "Per-template breakdown showing how many badges the organiser has "
            "created from each platform template."
        ),
    )
