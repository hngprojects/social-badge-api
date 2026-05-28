from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.sanitizer import validate_no_html


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
    email: EmailStr | None = Field(
        None,
        description="New email address.",
        json_schema_extra={"example": "jane@example.com"},
    )
    role: str | None = Field(
        None,
        description="The user's role or job title (e.g. 'Engineer', 'Designer').",
        json_schema_extra={"example": "Software Engineer"},
    )

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, val: str | None) -> str | None:
        if val is not None:
            val = val.strip()
            if not val:
                raise ValueError("First name cannot be empty")

            validate_no_html(val, "First name")

        return val

    @field_validator("last_name")
    @classmethod
    def validate_last_name(cls, val: str | None) -> str | None:
        if val is None:
            return None

        val = val.strip()
        if val:
            validate_no_html(val, "Last name")

        return val if val else None

    @field_validator("role")
    @classmethod
    def validate_role(cls, val: str | None) -> str | None:
        if val is None:
            return val
        val = val.strip()
        if val:
            validate_no_html(val, "Role/title")
        return val if val else None


class DeleteProfileResponse(BaseModel):
    """Response schema for successful profile deletion."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="The ID of the deleted user.",
        json_schema_extra={"example": "123e4567-e89b-12d3-a456-426614174000"},
    )
