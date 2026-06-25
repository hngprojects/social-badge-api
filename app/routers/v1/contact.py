from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from app.core.config import settings
from app.core.exceptions import EmailDeliveryError
from app.core.rate_limit import limiter
from app.schemas.contact import ContactRequest, ContactResponse, ContactSubjectOption
from app.schemas.response import ErrorResponse, SuccessResponse
from app.services.contact import get_contact_subjects, submit_contact_form

router = APIRouter()


@router.get(
    "/subjects",
    response_model=SuccessResponse[list[ContactSubjectOption]],
    status_code=status.HTTP_200_OK,
    summary="List contact form subject options",
    description=(
        "Returns all available subject categories for the contact form dropdown. "
        "Each entry contains the enum value (to submit) and a human-readable label."
    ),
    responses={
        200: {
            "description": "Subject options retrieved successfully.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Contact subject options retrieved successfully",
                        "data": [
                            {"value": "general", "label": "General Question"},
                            {"value": "partnership", "label": "Partnership Idea"},
                            {"value": "bug_report", "label": "Bug Report"},
                            {"value": "feedback", "label": "Feedback"},
                            {"value": "billing", "label": "Billing"},
                            {"value": "other", "label": "Other"},
                        ],
                    }
                }
            },
        },
        429: {
            "model": ErrorResponse,
            "description": "Rate limit exceeded.",
        },
    },
)
@limiter.limit("30/minute")
async def list_contact_subjects(
    request: Request,
) -> SuccessResponse[list[ContactSubjectOption]]:
    """
    Retrieves all available subjects for the contact form.

    Serves categories like bug reports, feedback, and billing that users can select. This public endpoint requires no authentication, responds very quickly without database queries by returning static enum values, and is rate-limited to 30 requests per minute per client IP.
    """
    return SuccessResponse(
        message="Contact subject options retrieved successfully",
        data=get_contact_subjects(),
    )


@router.post(
    "",
    response_model=SuccessResponse[ContactResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Submit a contact form message",
    description=(
        """
        Submits a contact form.

        Generates a unique reference ID for the submission,
        sends a notification email to the Flare Tag team and an
        auto-reply confirmation to the sender.
        """
        "No authentication is required. "
        "Rate-limited to 5 requests per IP per minute to prevent spam."
    ),
    responses={
        201: {
            "description": "Message received and notification dispatched.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": (
                            "Thanks for reaching out! "
                            "We'll get back to you within one business day."
                        ),
                        "data": {
                            "reference_id": "CONTACT-2026-A1B2C3",
                            "email": "alex@yourcompany.com",
                        },
                    }
                }
            },
        },
        422: {
            "model": ErrorResponse,
            "description": "Validation error in the payload.",
        },
        429: {
            "model": ErrorResponse,
            "description": "Rate limit exceeded.",
        },
        502: {
            "model": ErrorResponse,
            "description": "Email delivery failed — message was not sent.",
        },
    },
)
@limiter.limit("5/minute")
async def contact_us(
    request: Request,
    payload: ContactRequest,
) -> Any:
    """
    Submits a message using the contact form and triggers email notifications.

    Validates the contact request payload, generates a unique reference ID, sends an alert email to the support team, and dispatches a confirmation email to the user. This is a public endpoint open to any visitor, rate-limited to 5 requests per minute per IP to protect against spam. Outgoing SMTP network requests block the thread, so response time depends directly on the email service provider's performance.
    """
    try:
        reference_id = await submit_contact_form(payload)
    except EmailDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "We could not deliver your message due to an email service error. "
                "Please try again or email us directly at "
                f"{settings.CONTACT_RECIPIENT_EMAIL}."
            ),
        ) from exc

    return SuccessResponse(
        message=(
            "Thanks for reaching out! We'll get back to you within one business day."
        ),
        data=ContactResponse(
            reference_id=reference_id,
            email=payload.email,
        ),
    )
