import logging

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)

from app.core.config import settings
from app.core.exceptions import CloudinaryUploadError, InvalidCredentialsError
from app.core.rate_limit import limiter
from app.dependencies import CurrentUser, DBSession, RedisClient
from app.schemas.auth import UserResponse
from app.schemas.profile import (
    ChangePasswordRequest,
    DeleteProfileResponse,
    UpdateProfileRequest,
)
from app.schemas.response import ErrorResponse, SuccessResponse
from app.services.profile import (
    change_password,
    delete_profile,
    remove_profile_photo,
    update_profile,
    update_profile_photo,
)

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024
CHUNK_SIZE = 8 * 1024

IMAGE_MAGIC_BYTES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89\x50\x4e\x47": "image/png",
    b"\x47\x49\x46\x38": "image/gif",
}


def _validate_image_content(content: bytes) -> str:
    """
    Validates image content by checking magic bytes for supported formats (JPEG, PNG, GIF).

    This internal utility function inspects the header bytes of the uploaded file and inherits context from calling endpoints. It uses a very fast in-memory prefix comparison with no rate limiting applied.
    """
    if len(content) < 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is too small to be a valid image",
        )

    for magic_bytes, mime_type in IMAGE_MAGIC_BYTES.items():
        if content.startswith(magic_bytes):
            return mime_type

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid file format. Only JPEG, PNG, and GIF are supported.",
    )


async def _read_file_with_size_check(file: UploadFile, max_size: int) -> bytes:
    """
    Reads incoming file streams in chunks while enforcing size limits.

    Aborts reading early if the accumulated size exceeds the limit, preventing excessively large files from loading into server memory. This internal utility function uses no authentication or rate limiting.
    """
    chunks: list[bytes] = []
    total_size = 0

    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break

        total_size += len(chunk)

        if total_size > max_size:
            max_mb = int(max_size / 1024 / 1024)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size exceeds maximum allowed size of {max_mb} MB",
            )

        chunks.append(chunk)

    return b"".join(chunks)


@router.get(
    "",
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
    """
    Retrieves the authenticated organiser's profile details.

    Requires authenticated session access. It introduces extremely low overhead by returning the user entity already loaded by the dependencies and is rate-limited to 10 requests per minute per IP.
    """

    return SuccessResponse(
        message="Profile retrieved successfully",
        data=UserResponse.model_validate(current_user),
    )


@router.put(
    "",
    response_model=SuccessResponse[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Update user profile",
    description=(
        "Update profile information (first name, last name, email, and/or role). "
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
    """
    Updates profile details of the authenticated organiser.

    Modifies editable details such as names, email, and roles. This endpoint requires authenticated session access, executes database update queries on the users table immediately, and is rate-limited to 5 requests per minute per IP.
    """

    if (
        payload.first_name is None
        and payload.last_name is None
        and payload.email is None
        and payload.role is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field must be provided",
        )

    updated_user = await update_profile(
        session=session,
        user=current_user,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        role=payload.role,
    )

    logger.info("Updated profile for user %s", current_user.id)

    return SuccessResponse(
        message="Profile updated successfully",
        data=UserResponse.model_validate(updated_user),
    )


@router.delete(
    "",
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
    response: Response,
    session: DBSession,
    redis: RedisClient,
    current_user: CurrentUser,
) -> SuccessResponse[DeleteProfileResponse]:
    """
    Permanently deletes the user profile and all associated data.

    Removes the user record, associated refresh tokens, and preferences, and deletes browser session cookies. This endpoint requires authenticated session access, runs heavy cascading deletes across multiple database tables, and is rate-limited to 5 requests per minute per IP.
    """

    user_id = current_user.id
    refresh_token = request.cookies.get(settings.REFRESH_COOKIE)
    access_token = request.cookies.get(settings.ACCESS_COOKIE)

    await delete_profile(
        session=session,
        redis=redis,
        user_id=user_id,
        access_token=access_token,
        refresh_token=refresh_token,
    )

    response.delete_cookie(
        key=settings.REFRESH_COOKIE,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )
    response.delete_cookie(
        key=settings.ACCESS_COOKIE,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )

    logger.info("Deleted profile for user %s", user_id)

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
        "If the user already has a profile photo, the old one is "
        "automatically deleted. "
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
    file: UploadFile = File(  # noqa: B008
        ..., description="Image file (JPEG, PNG, GIF)"
    ),
) -> SuccessResponse[UserResponse]:
    """
    Uploads or updates the authenticated user's profile photo.

    Validates file size and format, executes outgoing Cloudinary network calls to save the new image and delete the old asset, and updates the user's photo URL. This endpoint requires authenticated session access, involves block-wise stream reading, and is rate-limited to 10 requests per minute per IP.
    """

    content = await _read_file_with_size_check(file, MAX_FILE_SIZE)

    actual_mime_type = _validate_image_content(content)

    logger.info(
        f"Processing profile photo upload for user {current_user.id}: "
        f"claimed={file.content_type}, actual={actual_mime_type}"
    )

    try:
        updated_user = await update_profile_photo(
            session=session,
            user=current_user,
            photo_data=content,
        )
    except CloudinaryUploadError as exc:
        logger.exception(
            "Cloudinary upload failed for user %s: %s", current_user.id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to upload image to Cloudinary",
        ) from exc

    logger.info("Updated profile photo for user %s", current_user.id)

    return SuccessResponse(
        message="Profile photo updated successfully",
        data=UserResponse.model_validate(updated_user),
    )


@router.delete(
    "/photo",
    response_model=SuccessResponse[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Remove profile photo",
    description=(
        "Delete the authenticated user's profile photo. "
        "The image is removed from Cloudinary and the profile_photo_url is cleared. "
        "If the user has no photo, the request succeeds with no side-effects."
    ),
    responses={
        200: {"description": "Profile photo removed successfully"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
@limiter.limit("10/minute")
async def remove_profile_photo_endpoint(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
) -> SuccessResponse[UserResponse]:
    """
    Removes the authenticated user's profile photo.

    Deletes the profile image from Cloudinary and clears the photo URL in the database. This endpoint requires authenticated session access, performs a remote network delete request and database write transaction, and is rate-limited to 10 requests per minute per IP.
    """

    updated_user = await remove_profile_photo(session=session, user=current_user)

    logger.info("Removed profile photo for user %s", current_user.id)

    return SuccessResponse(
        message="Profile photo removed successfully",
        data=UserResponse.model_validate(updated_user),
    )


@router.put(
    "/password/change",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Change password",
    description=(
        "Change the authenticated user's password. "
        "Requires the current password for verification. "
        "The new password must meet complexity requirements and differ "
        "from the current password."
    ),
    responses={
        200: {"description": "Password changed successfully"},
        401: {
            "model": ErrorResponse,
            "description": "Not authenticated or current password is incorrect",
        },
        422: {"model": ErrorResponse, "description": "Validation error"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
@limiter.limit("5/minute")
async def change_user_password(
    request: Request,
    session: DBSession,
    redis: RedisClient,
    current_user: CurrentUser,
    payload: ChangePasswordRequest,
) -> SuccessResponse[None]:
    """
    Changes the authenticated user's password.

    Verifies the current password, performs CPU-heavy password hashing to encrypt the new password, updates the database, and invalidates other active sessions. This endpoint requires authenticated session access, runs a write transaction on the database, and is rate-limited to 5 requests per minute per IP.
    """

    access_token = request.cookies.get(settings.ACCESS_COOKIE)
    refresh_token = request.cookies.get(settings.REFRESH_COOKIE)
    try:
        await change_password(
            session=session,
            redis=redis,
            user=current_user,
            payload=payload,
            access_token=access_token,
            refresh_token=refresh_token,
        )
    except InvalidCredentialsError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        ) from err

    logger.info("Password changed for user %s", current_user.id)

    return SuccessResponse(
        message="Password changed successfully",
        data=None,
    )
