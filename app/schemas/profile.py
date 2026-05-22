from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.auth import UserResponse


class UpdateProfileRequest(BaseModel):
    """Request schema for updating user profile."""

    first_name: str | None = Field(
        None,
        description="The first name of the organiser.",
        json_schema_extra={"example": "Jane", "minLength": 1},
    )
    last_name: str | None = Field(
        None,
        description="The last name of the organiser.",
        json_schema_extra={"example": "Doe", "minLength": 0},
    )

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, val: str | None) -> str | None:
        if val is not None and not val.strip():
            raise ValueError("First name cannot be empty")
        return val.strip() if val else None

    @field_validator("last_name")
    @classmethod
    def validate_last_name(cls, val: str | None) -> str | None:
        if val is None:
            return None
        return val.strip() if val.strip() else None


class DeleteProfileResponse(BaseModel):
    """Response schema for successful profile deletion."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="The ID of the deleted user.",
        json_schema_extra={"example": "123e4567-e89b-12d3-a456-426614174000"},
    )
