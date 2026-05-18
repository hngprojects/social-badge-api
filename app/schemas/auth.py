from datetime import datetime
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

from app.core.security import validate_password_strength


class SignupRequest(BaseModel):
    first_name: str = Field(
        ...,
        description="The first name of the organiser.",
        json_schema_extra={"example": "Jane", "minLength": 1},
    )
    last_name: str | None = Field(
        None,
        description="The last name of the organiser.",
        json_schema_extra={"example": "Doe", "minLength": 0},
    )
    email: EmailStr = Field(
        ...,
        description="A valid email address that will be used for login.",
        json_schema_extra={"example": "jane@example.com"},
    )
    password: str = Field(
        ...,
        description=(
            "Must contain at least one uppercase, one lowercase, "
            "one number, and one special character."
        ),
        json_schema_extra={
            "example": "StrongPassword1!",
            "minLength": 8,
            "maxLength": 72,
        },
    )

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, val: str) -> str:
        if not val or not val.strip():
            raise ValueError("First name cannot be empty")
        return val.strip()

    @field_validator("last_name")
    @classmethod
    def validate_last_name(cls, val: str | None) -> str | None:
        if val is None:
            return None
        return val.strip()

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, val: Any) -> Any:
        if isinstance(val, str):
            return val.strip().lower()
        return val

    @field_validator("password")
    @classmethod
    def validate_password(cls, val: str) -> str:
        return validate_password_strength(val)


# Schema for the resend verification token request payload. Emmanuel
class ResendVerificationRequest(BaseModel):
    email: EmailStr = Field(
        ...,
        description="The email address to resend the verification token to.",
        json_schema_extra={"example": "jane@example.com"},
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, val: Any) -> Any:
        if isinstance(val, str):
            return val.strip().lower()
        return val


class VerifyEmailRequest(BaseModel):
    token: str = Field(
        ...,
        description="The one-time verification token",
        json_schema_extra={"example": "abcdef123456"},
    )


class LoginRequest(BaseModel):
    email: EmailStr = Field(
        ...,
        description="A valid email address that will be used for login.",
        json_schema_extra={"example": "jane@example.com"},
    )
    password: str = Field(
        ...,
        description=(
            "Must contain at least one uppercase, one lowercase, "
            "one number, and one special character."
        ),
        json_schema_extra={"example": "StrongPassword1!", "minLength": 8},
    )


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(
        ...,
        description="The email address associated with the user account.",
        json_schema_extra={"example": "dave@example.com"},
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, val: Any) -> Any:
        if isinstance(val, str):
            return val.strip().lower()
        return val


class ResetPasswordRequest(BaseModel):
    token: str = Field(
        ...,
        min_length=1,
        description="Password reset token sent to the user's email.",
        json_schema_extra={"example": "reset-token-from-email"},
    )
    new_password: str = Field(
        ...,
        description=(
            "Must contain at least one uppercase, one lowercase, "
            "one number, and one special character."
        ),
        json_schema_extra={
            "example": "NewStrongPassword1!",
            "minLength": 8,
            "maxLength": 72,
        },
    )
    confirm_password: str = Field(
        ...,
        description="Must match new password.",
        json_schema_extra={
            "example": "NewStrongPassword1!",
            "minLength": 8,
            "maxLength": 72,
        },
    )

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, val: str) -> str:
        return validate_password_strength(val)

    @model_validator(mode="after")
    def validate_password_match(self) -> "ResetPasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class GoogleExchangeRequest(BaseModel):
    code: str = Field(
        ...,
        description="The one-time exchange code received after Google OAuth callback.",
    )


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    id: UUID = Field(
        ...,
        description="The unique identifier for the user.",
        json_schema_extra={"example": "123e4567-e89b-12d3-a456-426614174000"},
    )

    first_name: str = Field(
        ...,
        description="The first name of the organiser.",
        json_schema_extra={"example": "Jane"},
    )
    last_name: str | None = Field(
        None,
        description="The last name of the organiser.",
        json_schema_extra={"example": "Doe"},
    )
    email: EmailStr = Field(
        ...,
        description="The email address registered.",
        json_schema_extra={"example": "jane@example.com"},
    )

    is_email_verified: bool = Field(
        ...,
        description="Whether the user's email has been verified.",
        json_schema_extra={"example": False},
    )
    profile_photo_url: str | None = Field(
        None,
        description="Optional URL to the user's profile photo.",
        json_schema_extra={"example": "https://example.com/photo.jpg"},
    )
    created_at: datetime = Field(
        ...,
        description="The timestamp when the user account was created.",
        json_schema_extra={"example": "2026-05-09T05:28:33Z"},
    )
    updated_at: datetime = Field(
        ...,
        description="The timestamp when the user account was last updated.",
        json_schema_extra={"example": "2026-05-09T05:28:33Z"},
    )

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, val: Any) -> Any:
        if val is not None and not isinstance(val, UUID | str | bytes):
            return str(val)
        return val


class LoginResponse(BaseModel):
    user: UserResponse = Field(
        ...,
        description="The authenticated user's profile details.",
    )
