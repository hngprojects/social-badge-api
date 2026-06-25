from fastapi import APIRouter, HTTPException, Request, status

from app.core.rate_limit import limiter
from app.dependencies import DBSession
from app.schemas.newsletter import (
    NewsletterSubscribeRequest,
    NewsletterSubscribeResponse,
    NewsletterUnsubscribeRequest,
)
from app.schemas.response import ErrorResponse, SuccessResponse
from app.services.newsletter import subscribe, unsubscribe

router = APIRouter()


@router.post(
    "/subscribe",
    response_model=SuccessResponse[NewsletterSubscribeResponse],
    status_code=status.HTTP_200_OK,
    summary="Subscribe to the newsletter",
    responses={
        200: {"description": "Subscribed (new or already active)."},
        422: {"model": ErrorResponse, "description": "Validation error."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("5/minute")
async def subscribe_to_newsletter(
    request: Request,
    session: DBSession,
    payload: NewsletterSubscribeRequest,
) -> SuccessResponse[NewsletterSubscribeResponse]:
    """Subscribes an email address to the platform newsletter.

    Creates a new newsletter subscriber record in the database if the email does not
    exist, or returns a message indicating it is already subscribed. This public
    endpoint requires no authentication, commits the insert transaction immediately
    after querying the subscribers table, and is rate-limited to 5 requests per minute
    per client IP to mitigate spam.
    """
    subscriber, created = await subscribe(session=session, email=str(payload.email))
    message = (
        "You have successfully subscribed to the newsletter."
        if created
        else "This email address is already subscribed."
    )
    return SuccessResponse(
        message=message,
        data=NewsletterSubscribeResponse(
            email=subscriber.email,
            subscribed_at=subscriber.subscribed_at,
        ),
    )


@router.post(
    "/unsubscribe",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Unsubscribe from the newsletter",
    responses={
        200: {"description": "Unsubscribed successfully."},
        404: {"model": ErrorResponse, "description": "Token not found."},
        422: {"model": ErrorResponse, "description": "Validation error."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("5/minute")
async def unsubscribe_from_newsletter(
    request: Request,
    session: DBSession,
    payload: NewsletterUnsubscribeRequest,
) -> SuccessResponse[None]:
    """Unsubscribes from the newsletter using the token from the confirmation email.

    Validates the cryptographically signed unsubscribe token sent via email, queries the
    database, and deletes or marks the subscriber accordingly. This public endpoint uses
    the token itself as authorization and is rate-limited to 5 requests per minute per
    client IP.
    """
    found = await unsubscribe(session=session, token=payload.token)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unsubscribe token not found.",
        )
    return SuccessResponse(message="You have been unsubscribed from the newsletter.")
