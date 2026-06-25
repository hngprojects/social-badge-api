from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.core.sanitizer import validate_no_html
from app.core.security import validate_password_strength


class UpdateProfileRequest(BaseModel):
    """
    Data transfer object representing a request to update user profile information,
    validating names, email normalization, and job role constraints.
    """

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
        max_length=200,
        description="The user's role or job title (e.g. 'Engineer', 'Designer').",
        json_schema_extra={"example": "Software Engineer"},
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, val: Any) -> Any:
        """
        Trims surrounding whitespace and converts the email address to lowercase
        if a string email is provided.
        """
        if val is None:
            return val
        if isinstance(val, str):
            return val.strip().lower()
        return val

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, val: str | None) -> str | None:
        """
        Validates the optional first name by ensuring it is not empty when provided
        and contains no HTML content.
        """
        if val is not None:
            val = val.strip()
            if not val:
                raise ValueError("First name cannot be empty")

            validate_no_html(val, "First name")

        return val

    @field_validator("last_name")
    @classmethod
    def validate_last_name(cls, val: str | None) -> str | None:
        """
        Sanitizes and validates the optional last name by stripping whitespace
        and removing HTML tags.
        """
        if val is None:
            return None

        val = val.strip()
        if val:
            validate_no_html(val, "Last name")

        return val if val else None

    @field_validator("role")
    @classmethod
    def validate_role(cls, val: str | None) -> str | None:
        """
        Sanitizes and validates the optional user role or job title
        by stripping whitespace and removing HTML tags.
        """
        if val is None:
            return val
        val = val.strip()
        if val:
            validate_no_html(val, "Role/title")
        return val if val else None


class DeleteProfileResponse(BaseModel):
    """
    Data transfer object representing the response after a user profile
    is successfully deleted, returning the unique ID of the deleted user.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="The ID of the deleted user.",
        json_schema_extra={"example": "123e4567-e89b-12d3-a456-426614174000"},
    )


class ChangePasswordRequest(BaseModel):
    """
    Data transfer object representing a request to change the user's password,
    requiring the current password, a strong new password,
    and matching password confirmation.
    """

    current_password: str = Field(
        ...,
        description="The user's current password.",
        json_schema_extra={"example": "OldPassword1!"},
    )
    new_password: str = Field(
        ...,
        description=(
            "Must contain at least one uppercase letter, one lowercase letter, "
            "one number, and one special character."
        ),
        json_schema_extra={"example": "NewPassword1!"},
    )
    confirm_password: str = Field(
        ...,
        description="Must match new_password exactly.",
        json_schema_extra={"example": "NewPassword1!"},
    )

    @field_validator("current_password")
    @classmethod
    def validate_current_password_length(cls, val: str) -> str:
        """
        Enforces a maximum length constraint of 500 bytes on the current password input.
        """
        if len(val.encode("utf-8")) > 500:
            raise ValueError("current_password must not exceed 500 bytes")
        return val

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, val: str) -> str:
        """
        Enforces a maximum length constraint of 500 bytes on the new password
        and validates its strength.
        """
        if len(val.encode("utf-8")) > 500:
            raise ValueError("new_password must not exceed 500 bytes")
        return validate_password_strength(val)

    @field_validator("confirm_password")
    @classmethod
    def validate_confirm_password_length(cls, val: str) -> str:
        """
        Enforces a maximum length constraint of 500 bytes on the password confirmation
        input.
        """
        if len(val.encode("utf-8")) > 500:
            raise ValueError("confirm_password must not exceed 500 bytes")
        return val

    @model_validator(mode="after")
    def passwords_must_match(self) -> ChangePasswordRequest:
        """
        Ensures that the new password and confirm password fields match exactly.
        """
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self

    @model_validator(mode="after")
    def new_must_differ_from_current(self) -> ChangePasswordRequest:
        """Ensures that the new password differs from the current password."""
        if self.current_password == self.new_password:
            raise ValueError("New password must differ from the current password")
        return self
