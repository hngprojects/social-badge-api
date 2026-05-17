from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateTemplateInstanceRequest(BaseModel):
    platform_template_id: UUID = Field(
        ...,
        description="The id of the platform template the organiser is starting from.",
        json_schema_extra={"example": "019e1b66-c4ec-7b80-8c85-84c2fe4f9c84"},
    )


class TemplateInstanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    instance_id: UUID = Field(
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


class PublishedTemplateResponse(BaseModel):
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
