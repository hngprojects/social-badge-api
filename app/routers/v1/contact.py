from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from app.core.config import settings
from app.core.exceptions import EmailDeliveryError
from app.core.rate_limit import limiter
from app.schemas.contact import ContactRequest, ContactResponse
from app.schemas.response import ErrorResponse, SuccessResponse
from app.services.contact import submit_contact_form

router = APIRouter()


@router.post(
    "/",
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
