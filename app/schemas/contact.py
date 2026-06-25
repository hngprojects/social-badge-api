from enum import StrEnum
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.sanitizer import validate_no_html


class ContactTopic(StrEnum):
    """Enumeration of the supported topics or categories for contact form inquiries."""

    GENERAL = "general"
    PARTNERSHIP = "partnership"
    BUG_REPORT = "bug_report"
    FEEDBACK = "feedback"
    BILLING = "billing"
    OTHER = "other"


class ContactRequest(BaseModel):
    """Data transfer object representing a contact form submission, enforcing validation
    on the sender name, email, topic, and message content."""

    first_name: str = Field(
        ...,
        description="The sender's first name.",
        json_schema_extra={"example": "Alex", "minLength": 1},
    )
    last_name: str | None = Field(
        None,
        description="The sender's last name (optional).",
        json_schema_extra={"example": "Rivera"},
    )
    email: EmailStr = Field(
        ...,
        description="The sender's email address for replies.",
        json_schema_extra={"example": "alex@yourcompany.com"},
    )
    subject: ContactTopic = Field(
        ...,
        description="The topic/category of the message.",
        json_schema_extra={"example": "general"},
    )
    message: str = Field(
        ...,
        description="The body of the message. More detail helps us respond faster.",
        json_schema_extra={
            "example": "I have a question about setting up my first badge template.",
            "minLength": 10,
            "maxLength": 500,
        },
    )

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, val: str) -> str:
        """Sanitizes the sender's first name by trimming whitespace and ensuring it does
        not contain HTML tags."""
        if not val or not val.strip():
            raise ValueError("First name cannot be empty")
        return validate_no_html(val.strip(), "First name")

    @field_validator("last_name")
    @classmethod
    def validate_last_name(cls, val: str | None) -> str | None:
        """Sanitizes the optional last name by trimming whitespace and ensuring it does
        not contain HTML tags, returning None if empty."""
        if val is None:
            return None
        stripped = val.strip()
        if stripped:
            validate_no_html(stripped, "Last name")
        return stripped if stripped else None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, val: Any) -> Any:
        """Normalizes the email address by trimming surrounding whitespace and
        converting it to lowercase."""
        if isinstance(val, str):
            return val.strip().lower()
        return val

    @field_validator("message")
    @classmethod
    def validate_message(cls, val: str) -> str:
        """Validates the contact message body by enforcing length limits of 10 to 500
        characters and rejecting HTML tags."""
        stripped = val.strip()
        if len(stripped) < 10:
            raise ValueError("Message must be at least 10 characters long")
        if len(stripped) > 500:
            raise ValueError("Message must not exceed 500 characters")
        return validate_no_html(stripped, "Message")


class ContactResponse(BaseModel):
    """Data transfer object representing the response after a contact inquiry is
    successfully received, providing a tracking reference ID."""

    reference_id: str = Field(
        ...,
        description="A unique reference ID the sender can use to follow up.",
        json_schema_extra={"example": "CONTACT-2026-A1B2C3"},
    )
    email: EmailStr = Field(
        ...,
        description="The email address we will reply to.",
        json_schema_extra={"example": "alex@yourcompany.com"},
    )


class ContactSubjectOption(BaseModel):
    """Schema representing a single subject or topic option in the contact dropdown
    list, providing both the raw enum value and a user-friendly label."""

    value: str = Field(
        ...,
        description="The enum value to submit in the contact form payload.",
        json_schema_extra={"example": "general"},
    )
    label: str = Field(
        ...,
        description="Human-readable label for the dropdown option.",
        json_schema_extra={"example": "General Question"},
    )
