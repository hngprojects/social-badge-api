from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.core.rate_limit import limiter
from app.dependencies import CurrentUser, DBSession
from app.schemas.notification import (
    MarkAllReadResponse,
    NotificationListResponse,
    NotificationPreferencesResponse,
    NotificationResponse,
    UnreadCountResponse,
    UpdateNotificationPreferencesRequest,
)
from app.schemas.response import ErrorResponse, SuccessResponse
from app.services.notification import (
    get_notification_preferences,
    get_unread_count,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    update_notification_preferences,
)

router = APIRouter()

INVALID_PREFERENCE_ERROR = "Request body must include at least one preference field."


@router.get(
    "",
    response_model=SuccessResponse[NotificationPreferencesResponse],
    status_code=status.HTTP_200_OK,
    summary="Get notification preferences",
    description=(
        "Returns the authenticated organiser's current notification preferences. "
        "Organisers who have never saved preferences receive the defaults "
        "(all notifications on) rather than a 404."
    ),
    responses={
        200: {"description": "Preferences retrieved."},
        401: {"model": ErrorResponse, "description": "Not authenticated."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("30/minute")
async def get_preferences(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
) -> SuccessResponse[NotificationPreferencesResponse]:
    """Return the current organiser's notification preferences."""
    prefs = await get_notification_preferences(
        session=session,
        user_id=current_user.id,
    )
    return SuccessResponse(
        message="Notification preferences retrieved successfully.",
        data=prefs,
    )


@router.patch(
    "",
    response_model=SuccessResponse[NotificationPreferencesResponse],
    status_code=status.HTTP_200_OK,
    summary="Update notification preferences",
    description=(
        "Partially updates the authenticated organiser's notification preferences. "
        "Only fields present in the request body are written — absent fields are "
        "left unchanged. Unknown keys are silently ignored. "
        "An empty body returns 400."
    ),
    responses={
        200: {"description": "Preferences updated."},
        400: {
            "model": ErrorResponse,
            "description": "Request body contains no known preference fields.",
        },
        401: {"model": ErrorResponse, "description": "Not authenticated."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("30/minute")
async def patch_preferences(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    payload: UpdateNotificationPreferencesRequest | None = None,
) -> SuccessResponse[NotificationPreferencesResponse]:
    """Apply a partial update to the organiser's notification preferences."""
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=INVALID_PREFERENCE_ERROR,
        )

    # Strip fields the client left as None (not sent).
    updates = {key: val for key, val in payload.model_dump().items() if val is not None}

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=INVALID_PREFERENCE_ERROR,
        )

    prefs = await update_notification_preferences(
        session=session,
        user_id=current_user.id,
        updates=updates,
    )
    return SuccessResponse(
        message="Notification preferences updated successfully.",
        data=prefs,
    )


@router.get(
    "/list",
    response_model=SuccessResponse[NotificationListResponse],
    status_code=status.HTTP_200_OK,
    summary="List the organiser's notifications",
    description=(
        "Returns a paginated list of the authenticated organiser's "
        "notifications, newest first. Both read and unread are returned; "
        "the frontend handles grouping by date."
    ),
    responses={
        200: {"description": "Notifications retrieved."},
        401: {"model": ErrorResponse, "description": "Not authenticated."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("60/minute")
async def list_user_notifications(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> SuccessResponse[NotificationListResponse]:
    notifications, total = await list_notifications(
        session=session,
        user_id=current_user.id,
        page=page,
        limit=limit,
    )

    base_url = "/api/v1/organiser/notifications/list"
    prev_link = f"{base_url}?page={page - 1}&limit={limit}" if page > 1 else None
    next_link = (
        f"{base_url}?page={page + 1}&limit={limit}" if page * limit < total else None
    )

    return SuccessResponse(
        message="Notifications retrieved successfully.",
        data=NotificationListResponse(
            notifications=[
                NotificationResponse.model_validate(n) for n in notifications
            ],
            total=total,
            page=page,
            limit=limit,
            prev=prev_link,
            next=next_link,
        ),
    )


@router.get(
    "/unread-count",
    response_model=SuccessResponse[UnreadCountResponse],
    status_code=status.HTTP_200_OK,
    summary="Get unread notification count",
    description="Returns the number of unread notifications for the bell badge.",
    responses={
        200: {"description": "Count retrieved."},
        401: {"model": ErrorResponse, "description": "Not authenticated."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("120/minute")
async def get_unread_notifications_count(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
) -> SuccessResponse[UnreadCountResponse]:
    count = await get_unread_count(session=session, user_id=current_user.id)
    return SuccessResponse(
        message="Unread count retrieved successfully.",
        data=UnreadCountResponse(unread_count=count),
    )


@router.post(
    "/{notification_id}/mark-read",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Mark one notification as read",
    responses={
        200: {"description": "Notification marked as read."},
        401: {"model": ErrorResponse, "description": "Not authenticated."},
        404: {"model": ErrorResponse, "description": "Notification not found."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("60/minute")
async def mark_one_read(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    notification_id: UUID,
) -> SuccessResponse[None]:
    found = await mark_notification_read(
        session=session,
        user_id=current_user.id,
        notification_id=notification_id,
    )
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        )
    return SuccessResponse(message="Notification marked as read.")


@router.post(
    "/mark-all-read",
    response_model=SuccessResponse[MarkAllReadResponse],
    status_code=status.HTTP_200_OK,
    summary="Mark all notifications as read",
    responses={
        200: {"description": "Notifications marked as read."},
        401: {"model": ErrorResponse, "description": "Not authenticated."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("30/minute")
async def mark_all_read(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
) -> SuccessResponse[MarkAllReadResponse]:
    marked = await mark_all_notifications_read(
        session=session,
        user_id=current_user.id,
    )
    return SuccessResponse(
        message="All notifications marked as read.",
        data=MarkAllReadResponse(marked=marked),
    )
