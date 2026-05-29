import logging
from urllib.parse import unquote, urlparse
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CloudinaryUploadError
from app.models.users import User
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


async def update_profile(
    session: AsyncSession,
    user: User,
    first_name: str | None = None,
    last_name: str | None = None,
) -> User:
    """Update a user's profile information.

    Only updates fields that are explicitly provided (not None).

    Args:
        session: The database session.
        user: The user object to update.
        first_name: New first name (optional).
        last_name: New last name (optional).

    Returns:
        The updated user object.
    """
    if first_name is not None:
        user.first_name = first_name
    if last_name is not None:
        user.last_name = last_name

    session.add(user)
    await session.commit()
    await session.refresh(user)

    return user


async def delete_profile(
    session: AsyncSession,
    user_id: UUID,
) -> None:
    """Delete a user's profile and associated assets.

    Fetches the user from the database to retrieve the profile photo URL,
    then attempts to delete the profile photo from Cloudinary if it exists.
    Even if Cloudinary deletion fails, the user profile is still deleted.

    Args:
        session: The database session.
        user_id: The ID of the user to delete.

    Raises:
        CloudinaryUploadError: If Cloudinary deletion fails (but this is logged
            and the user is still deleted).
    """
    # Fetch the user to get the profile photo URL
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalars().first()

    if user and user.profile_photo_url:
        public_id = _extract_cloudinary_public_id(user.profile_photo_url)
        if public_id:
            try:
                await delete_asset(public_id)
                logger.info(f"Deleted profile photo for user {user_id}: {public_id}")
            except CloudinaryUploadError as exc:
                logger.warning(
                    "Failed to delete profile photo from Cloudinary for user %s: %s",
                    user_id,
                    exc,
                )
                # Continue with user deletion even if Cloudinary fails
        else:
            logger.warning(
                f"Could not extract public_id from URL: {user.profile_photo_url}"
            )

    # Delete the user record from the database
    delete_stmt = delete(User).where(User.id == user_id)
    await session.execute(delete_stmt)
    await session.commit()

    logger.info(f"Deleted user profile: {user_id}")
