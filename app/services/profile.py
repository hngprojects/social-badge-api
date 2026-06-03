import asyncio
import logging
from urllib.parse import unquote, urlparse
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CloudinaryUploadError, InvalidCredentialsError
from app.core.security import hash_password, verify_password
from app.models.badges import Badge
from app.models.users import User
from app.schemas.profile import ChangePasswordRequest
from app.services.auth import logout_session
from app.services.cloudinary import delete_asset, upload_logo

logger = logging.getLogger(__name__)


def _extract_cloudinary_public_id(url: str) -> str | None:
    """Extract and normalize the public_id from a Cloudinary URL.

    Cloudinary URLs follow the pattern:
    https://res.cloudinary.com/{cloud_name}/image/upload/v{version}/{public_id}.{ext}

    This function extracts the public_id and normalizes it by:
    - Removing the version segment (v{digits}/)
    - Removing the file extension
    - Preserving folder paths within the public_id

    Args:
        url: The Cloudinary URL string.

    Returns:
        The normalized public_id string if successfully extracted, None otherwise.
    """
    try:
        parsed = urlparse(url)
        path_parts = parsed.path.split("/")

        # Find the /upload/ segment and get everything after it
        try:
            upload_index = path_parts.index("upload")
            if upload_index + 1 < len(path_parts):
                parts = path_parts[upload_index + 1 :]

                # Remove the version segment (e.g., "v1234567890")
                # Cloudinary URLs include /v{digits}/ after /upload/
                if parts and parts[0].startswith("v") and parts[0][1:].isdigit():
                    parts = parts[1:]

                # Ensure we still have parts after removing version
                if not parts:
                    return None

                # Remove the file extension from the last part
                # The public_id is everything before the final extension
                last_part = parts[-1]
                if "." in last_part:
                    # Remove extension but preserve the filename
                    parts[-1] = last_part.rsplit(".", 1)[0]

                # Join remaining parts and URL decode
                public_id = "/".join(parts)
                return unquote(public_id)
        except ValueError:
            # /upload/ not found in path
            pass
    except Exception as exc:
        logger.warning(f"Failed to extract Cloudinary public_id from URL: {exc}")

    return None


async def update_profile_photo(
    session: AsyncSession,
    user: User,
    photo_data: bytes,
) -> User:
    """Update a user's profile photo.

    Uploads the new photo to Cloudinary and updates the user's profile_photo_url.
    If the user had a previous photo, it is deleted from Cloudinary after the
    new upload and database update succeed.

    Args:
        session: The database session.
        user: The user object to update.
        photo_data: The image file bytes to upload.

    Returns:
        The updated user object.

    Raises:
        CloudinaryUploadError: If the upload to Cloudinary fails.
    """
    # Extract the old photo public_id, but don't delete it yet
    old_public_id = (
        _extract_cloudinary_public_id(user.profile_photo_url)
        if user.profile_photo_url
        else None
    )

    # Upload the new profile photo first (this may raise CloudinaryUploadError)
    url, public_id = await upload_logo(photo_data)
    user.profile_photo_url = url

    # Update the database
    session.add(user)
    await session.commit()
    await session.refresh(user)

    logger.info(f"Updated profile photo for user {user.id}: {public_id}")

    # Best-effort cleanup of old asset after successful update
    # If deletion fails, the old asset remains but the user has already moved on
    if old_public_id:
        try:
            await delete_asset(old_public_id)
            logger.info(
                f"Deleted old profile photo for user {user.id}: {old_public_id}"
            )
        except CloudinaryUploadError as exc:
            logger.warning(
                "Failed to delete old profile photo for user %s: %s", user.id, exc
            )

    return user


async def remove_profile_photo(
    session: AsyncSession,
    user: User,
) -> User:
    """Remove the authenticated user's profile photo.

    Clears profile_photo_url in the database and deletes the asset from
    Cloudinary. If the user has no photo, this is a no-op. Cloudinary
    deletion failure is logged but does not prevent the DB field from being
    cleared.

    Args:
        session: The database session.
        user: The user object whose photo should be removed.

    Returns:
        The updated user object with profile_photo_url set to None.
    """
    if user.profile_photo_url:
        public_id = _extract_cloudinary_public_id(user.profile_photo_url)
        user.profile_photo_url = None
        session.add(user)
        await session.commit()
        await session.refresh(user)

        if public_id:
            try:
                await delete_asset(public_id)
                logger.info("Deleted profile photo for user %s: %s", user.id, public_id)
            except CloudinaryUploadError as exc:
                logger.warning(
                    "Failed to delete profile photo from Cloudinary for user %s: %s",
                    user.id,
                    exc,
                )
    return user


async def update_profile(
    session: AsyncSession,
    user: User,
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
    role: str | None = None,
) -> User:
    """Update a user's profile information.

    Only updates fields that are explicitly provided (not None).

    Args:
        session: The database session.
        user: The user object to update.
        first_name: New first name (optional).
        last_name: New last name (optional).
        email: New email address (optional).
        role: New role/title (optional).

    Returns:
        The updated user object.
    """
    if first_name is not None:
        user.first_name = first_name
    if last_name is not None:
        user.last_name = last_name
    if email is not None:
        user.email = email
    if role is not None:
        user.role = role

    session.add(user)
    await session.commit()
    await session.refresh(user)

    return user


async def delete_profile(
    session: AsyncSession,
    redis: Redis,
    user_id: UUID,
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> None:
    """Delete a user's profile, associated Cloudinary assets, and invalidate sessions.

    Fetches the user and their badges to collect Cloudinary asset IDs,
    then deletes the user record from the database (the authoritative action).
    Cloudinary asset cleanup and session invalidation run as best-effort
    post-commit work so a DB failure never leaves orphaned side effects.

    Args:
        session: The database session.
        redis: Redis client for token blacklisting.
        user_id: The ID of the user to delete.
        access_token: The caller's raw access token cookie value.
        refresh_token: The caller's raw refresh token cookie value.
    """
    # Fetch the user to get the profile photo URL
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalars().first()

    # Collect all Cloudinary public IDs to delete
    public_ids_to_delete: list[str] = []

    if user and user.profile_photo_url:
        public_id = _extract_cloudinary_public_id(user.profile_photo_url)
        if public_id:
            public_ids_to_delete.append(public_id)
        else:
            logger.warning(
                "Could not extract public_id from URL: %s", user.profile_photo_url
            )

    # Fetch all badges belonging to this user and collect their Cloudinary assets
    badge_stmt = select(Badge).where(Badge.organiser_id == user_id)
    badge_result = await session.execute(badge_stmt)
    badges = badge_result.scalars().all()

    for badge in badges:
        if badge.logo_public_id:
            public_ids_to_delete.append(badge.logo_public_id)
        if badge.thumbnail_url:
            thumb_id = _extract_cloudinary_public_id(badge.thumbnail_url)
            if thumb_id:
                public_ids_to_delete.append(thumb_id)

    # Delete the user record from the database first (cascades to badges, tokens, etc.)
    # This is the authoritative action; external cleanup is best-effort post-commit.
    delete_stmt = delete(User).where(User.id == user_id)
    await session.execute(delete_stmt)
    await session.commit()

    logger.info("Deleted user profile: %s", user_id)

    # Best-effort post-commit: delete Cloudinary assets concurrently
    if public_ids_to_delete:
        results = await asyncio.gather(
            *(delete_asset(pid) for pid in public_ids_to_delete),
            return_exceptions=True,
        )
        for pid, res in zip(public_ids_to_delete, results, strict=False):
            if isinstance(res, Exception):
                logger.warning(
                    "Failed to delete Cloudinary asset %s for user %s: %s",
                    pid,
                    user_id,
                    res,
                )
            else:
                logger.info("Deleted Cloudinary asset %s for user %s", pid, user_id)

    # Best-effort post-commit: invalidate the current session (blacklist access token)
    try:
        await logout_session(session, redis, refresh_token, access_token)
    except Exception:
        logger.warning("Failed to invalidate session for deleted user %s", user_id)


async def change_password(
    session: AsyncSession,
    redis: Redis,
    user: User,
    payload: ChangePasswordRequest,
    access_token: str | None,
    refresh_token: str | None,
) -> None:
    """Change the authenticated user's password.

    Verifies the current password before applying the change, then
    revokes the caller's current session. The user will need to log in again
    with the new password.

    OAuth-only accounts (password_hash is None) receive the same
    InvalidCredentialsError as a wrong password to avoid leaking
    account auth method to the caller.

    Args:
        session: The database session.
        redis: Redis client for token blacklisting.
        user: The currently authenticated user.
        payload: Validated request containing current and new passwords.
        access_token: The caller's raw access token cookie value, used
            to blacklist it after the password is changed.

    Raises:
        InvalidCredentialsError: If current_password does not match the
            stored hash, or if the account has no password set.
    """
    if not user.password_hash or not await asyncio.to_thread(
        verify_password, payload.current_password, user.password_hash
    ):
        raise InvalidCredentialsError

    user.password_hash = await asyncio.to_thread(hash_password, payload.new_password)
    session.add(user)
    await session.commit()

    await logout_session(session, redis, refresh_token, access_token)
