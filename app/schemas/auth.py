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

from app.core.sanitizer import validate_no_html
from app.core.security import validate_password_strength


class SignupRequest(BaseModel):
    """
    Data transfer object representing a signup request, validating name sanitization,
    email format, and password complexity constraints.
    """

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
        """
        Sanitizes and validates the first name, ensuring it contains no HTML tags
        and is not empty.
        """
        if not val or not val.strip():
            raise ValueError("First name cannot be empty")

        return validate_no_html(val.strip(), "First name")

    @field_validator("last_name")
    @classmethod
    def validate_last_name(cls, val: str | None) -> str | None:
        """
        Sanitizes and validates the optional last name, removing HTML tags if present.
        """
        if val is None:
            return None

        val = val.strip()
        if val:
            validate_no_html(val, "Last name")

        return val

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, val: Any) -> Any:
        """
        Normalizes the email address input by stripping whitespace and converting it
        to lowercase.
        """
        if isinstance(val, str):
            return val.strip().lower()

        return val

    @field_validator("password")
    @classmethod
    def validate_password(cls, val: str) -> str:
        """
        Validates password input strength and enforces a maximum size constraint
        of 500 bytes.
        """
        if len(val.encode("utf-8")) > 500:
            raise ValueError("Password must not exceed 500 bytes")

        return validate_password_strength(val)


class ResendVerificationRequest(BaseModel):
    """
    Data transfer object representing a request to resend the verification email link.
    """

    email: EmailStr = Field(
        ...,
        description="The email address to resend the verification token to.",
        json_schema_extra={"example": "jane@example.com"},
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, val: Any) -> Any:
        """
        Normalizes the email address input by trimming surrounding whitespace
        and converting it to lowercase.
        """
        if isinstance(val, str):
            return val.strip().lower()
        return val


class VerifyEmailRequest(BaseModel):
    """
    Data transfer object containing the unique one-time token needed
    to verify a user's email address.
    """

    token: str = Field(
        ...,
        description="The one-time verification token",
        json_schema_extra={"example": "abcdef123456"},
    )


class LoginRequest(BaseModel):
    """
    Data transfer object representing a login request, validating email format
    and password length limits.
    """

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

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, val: str) -> str:
        """
        Validates that the password length does not exceed 500 characters.
        """
        if len(val.encode("utf-8")) > 500:
            raise ValueError("Password must not exceed 500 characters")

        return val


class ForgotPasswordRequest(BaseModel):
    """
    Data transfer object representing a forgot-password request,
    containing the user's registered email address.
    """

    email: EmailStr = Field(
        ...,
        description="The email address associated with the user account.",
        json_schema_extra={"example": "dave@example.com"},
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, val: Any) -> Any:
        """
        Normalizes the email address input by trimming surrounding whitespace
        and converting it to lowercase.
        """
        if isinstance(val, str):
            return val.strip().lower()
        return val


class ResetPasswordRequest(BaseModel):
    """
    Data transfer object representing a password reset request,
    validating password match and strength requirements.
    """

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
        """
        Validates that the new password does not exceed 500 characters
        and meets strength requirements.
        """
        if len(val.encode("utf-8")) > 500:
            raise ValueError("Password must not exceed 500 characters")

        return validate_password_strength(val)

    @model_validator(mode="after")
    def validate_password_match(self) -> ResetPasswordRequest:
        """
        Ensures that the new password and confirm password fields match exactly.
        """
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class UserResponse(BaseModel):
    """
    Data transfer object representing the user profile data response,
    mapping from database attributes.
    """

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
    role: str | None = Field(
        None,
        description="The user's role or job title.",
        json_schema_extra={"example": "Software Engineer"},
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
        """
        Converts the user ID value to a string representation if required.
        """
        if val is not None and not isinstance(val, UUID | str | bytes):
            return str(val)
        return val


class LoginUserResponse(BaseModel):
    """
    Minimal user payload returned only on login.

        Deliberately excludes internal IDs, timestamps, and third-party URLs
        to reduce the attack surface of the authentication response.
    """

    first_name: str = Field(..., json_schema_extra={"example": "Jane"})
    last_name: str | None = Field(None, json_schema_extra={"example": "Doe"})
    email: EmailStr = Field(..., json_schema_extra={"example": "jane@example.com"})
    is_email_verified: bool = Field(
        ...,
        description="Kept so the frontend can redirect unverified users appropriately.",
    )


class LoginResponse(BaseModel):
    """
    Data transfer object representing the successful login response,
    containing the user's minimal profile.
    """

    user: LoginUserResponse = Field(
        ...,
        description="Minimal user profile returned on successful authentication.",
    )


class SessionResponse(BaseModel):
    """
    Data transfer object representing detailed information about an active user session,
    mapping from database attributes.
    """

    model_config = ConfigDict(from_attributes=True)

    session_id: UUID = Field(..., description="The refresh token record ID.")
    user_agent: str | None = Field(None, description="Browser or client identifier.")
    ip_address: str | None = Field(None, description="Partially masked IP address.")
    created_at: datetime = Field(..., description="When this session was created.")
    last_used_at: datetime | None = Field(
        None, description="When this session last performed a token rotation."
    )
    expires_at: datetime = Field(..., description="When this session expires.")
    is_current: bool = Field(
        ..., description="True if this session matches the current refresh token."
    )


class SessionListResponse(BaseModel):
    """
    Data transfer object representing a paginated list of active user sessions.
    """

    sessions: list[SessionResponse]
    total: int
    page: int
    limit: int


class LogoutAllResponse(BaseModel):
    """
    Data transfer object representing the response after revoking all active user
    sessions, indicating the count of revoked sessions.
    """

    sessions_revoked: int = Field(..., description="Number of sessions terminated.")
