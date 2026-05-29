from enum import StrEnum
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.sanitizer import validate_no_html


class ContactTopic(StrEnum):
    GENERAL = "general"
    PARTNERSHIP = "partnership"
    BUG_REPORT = "bug_report"
    FEEDBACK = "feedback"
    BILLING = "billing"
    OTHER = "other"


class ContactRequest(BaseModel):
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
            "maxLength": 5000,
        },
    )

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, val: str) -> str:
        if not val or not val.strip():
            raise ValueError("First name cannot be empty")
        return validate_no_html(val.strip(), "First name")

    @field_validator("last_name")
    @classmethod
    def validate_last_name(cls, val: str | None) -> str | None:
        if val is None:
            return None
        stripped = val.strip()
        if stripped:
            validate_no_html(stripped, "Last name")
        return stripped if stripped else None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, val: Any) -> Any:
        if isinstance(val, str):
            return val.strip().lower()
        return val

    @field_validator("message")
    @classmethod
    def validate_message(cls, val: str) -> str:
        stripped = val.strip()
        if len(stripped) < 10:
            raise ValueError("Message must be at least 10 characters long")
        if len(stripped) > 5000:
            raise ValueError("Message must not exceed 5000 characters")
        return validate_no_html(stripped, "Message")


class ContactResponse(BaseModel):
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
