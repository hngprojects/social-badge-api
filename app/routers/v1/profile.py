"""Profile management endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from app.core.exceptions import CloudinaryUploadError
from app.core.rate_limit import limiter
from app.dependencies import CurrentUser, DBSession
from app.schemas.auth import UserResponse
from app.schemas.profile import DeleteProfileResponse, UpdateProfileRequest
from app.schemas.response import ErrorResponse, SuccessResponse
from app.services.profile import delete_profile, update_profile, update_profile_photo

logger = logging.getLogger(__name__)

router = APIRouter()

# Max file size: 10 MB
MAX_FILE_SIZE = 10 * 1024 * 1024


@router.get(
    "/",
    response_model=SuccessResponse[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
    description="Returns the authenticated user's profile information.",
    responses={
        200: {"description": "Profile retrieved successfully"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
@limiter.limit("10/minute")
async def get_profile(
    request: Request,
    current_user: CurrentUser,
) -> SuccessResponse[UserResponse]:
    """Retrieve the authenticated user's profile."""
    return SuccessResponse(
        message="Profile retrieved successfully",
        data=UserResponse.model_validate(current_user),
    )


@router.put(
    "/",
    response_model=SuccessResponse[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Update user profile",
    description=(
        "Update user profile information (first name and/or last name). "
        "At least one field must be provided. "
        "Other fields remain unchanged."
    ),
    responses={
        200: {"description": "Profile updated successfully"},
        400: {"model": ErrorResponse, "description": "No fields to update"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
@limiter.limit("5/minute")
async def update_user_profile(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    payload: UpdateProfileRequest,
) -> SuccessResponse[UserResponse]:
    """Update the authenticated user's profile.
    
    Allows updating first_name and/or last_name. At least one field
    must be provided to make a valid update request.
    """
    # Check that at least one field is being updated
    if payload.first_name is None and payload.last_name is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field (first_name or last_name) must be provided",
        )
    
    updated_user = await update_profile(
        session=session,
        user=current_user,
        first_name=payload.first_name,
        last_name=payload.last_name,
    )
    
    logger.info(f"Updated profile for user {current_user.id}")
    
    return SuccessResponse(
        message="Profile updated successfully",
        data=UserResponse.model_validate(updated_user),
    )


@router.delete(
    "/",
    response_model=SuccessResponse[DeleteProfileResponse],
    status_code=status.HTTP_200_OK,
    summary="Delete user profile",
    description=(
        "Permanently delete the authenticated user's profile and all associated data. "
        "This action cannot be undone. The user's profile photo will also be removed "
        "from Cloudinary if it exists."
    ),
    responses={
        200: {"description": "Profile deleted successfully"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
@limiter.limit("5/minute")
async def delete_user_profile(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
) -> SuccessResponse[DeleteProfileResponse]:
    """Delete the authenticated user's profile.
    
    Permanently removes the user account and all associated data,
    including the profile photo from Cloudinary if one exists.
    This action is irreversible.
    """
    user_id = current_user.id
    
    await delete_profile(
        session=session,
        user_id=user_id,
    )
    
    logger.info(f"Deleted profile for user {user_id}")
    
    return SuccessResponse(
        message="Your profile has been permanently deleted.",
        data=DeleteProfileResponse(
            id=user_id,
        ),
    )


@router.put(
    "/photo",
    response_model=SuccessResponse[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Upload or update user profile photo",
    description=(
        "Upload a new profile photo. The image is uploaded to Cloudinary. "
        "If the user already has a profile photo, the old one is automatically deleted. "
        "Supports JPEG, PNG, and GIF formats. Max file size: 10 MB."
    ),
    responses={
        200: {"description": "Profile photo updated successfully"},
        400: {"model": ErrorResponse, "description": "Invalid file or file too large"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
@limiter.limit("10/minute")
async def upload_profile_photo_endpoint(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    file: UploadFile = File(..., description="Image file (JPEG, PNG, GIF)"),
) -> SuccessResponse[UserResponse]:
    """Upload or update the authenticated user's profile photo.
    
    Accepts image files and uploads them to Cloudinary.
    The previous profile photo is automatically deleted if it exists.
    """
    # Validate file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE / 1024 / 1024:.0f} MB",
        )
    
    # Validate file type
    if file.content_type not in ["image/jpeg", "image/png", "image/gif"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only JPEG, PNG, and GIF are supported.",
        )
    
    try:
        updated_user = await update_profile_photo(
            session=session,
            user=current_user,
            photo_data=content,
        )
    except CloudinaryUploadError as exc:
        logger.error(f"Cloudinary upload failed for user {current_user.id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to upload image to Cloudinary",
        ) from exc
    
    logger.info(f"Updated profile photo for user {current_user.id}")
    
    return SuccessResponse(
        message="Profile photo updated successfully",
        data=UserResponse.model_validate(updated_user),
    )
