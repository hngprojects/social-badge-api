"""Newsletter subscription endpoints."""

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
    """Subscribe an email address to the newsletter."""
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
    """Unsubscribe using the token from the confirmation email."""
    found = await unsubscribe(session=session, token=payload.token)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unsubscribe token not found.",
        )
    return SuccessResponse(message="You have been unsubscribed from the newsletter.")
