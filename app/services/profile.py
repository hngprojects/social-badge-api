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
    """Extract the public_id from a Cloudinary URL.
    
    Cloudinary URLs follow the pattern:
    https://res.cloudinary.com/{cloud_name}/image/upload/{public_id}
    
    Args:
        url: The Cloudinary URL string.
    
    Returns:
        The public_id string if successfully extracted, None otherwise.
    """
    try:
        parsed = urlparse(url)
        path_parts = parsed.path.split("/")
        
        # Find the /upload/ segment and get everything after it
        try:
            upload_index = path_parts.index("upload")
            if upload_index + 1 < len(path_parts):
                # Join remaining parts in case public_id contains slashes
                public_id = "/".join(path_parts[upload_index + 1 :])
                # URL decode in case of special characters
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
    If the user had a previous photo, it is deleted from Cloudinary.
    
    Args:
        session: The database session.
        user: The user object to update.
        photo_data: The image file bytes to upload.
    
    Returns:
        The updated user object.
    
    Raises:
        CloudinaryUploadError: If the upload to Cloudinary fails.
    """
    # Delete the old profile photo if it exists
    if user.profile_photo_url:
        old_public_id = _extract_cloudinary_public_id(user.profile_photo_url)
        if old_public_id:
            try:
                await delete_asset(old_public_id)
                logger.info(f"Deleted old profile photo for user {user.id}: {old_public_id}")
            except CloudinaryUploadError as exc:
                logger.warning(
                    f"Failed to delete old profile photo from Cloudinary for user {user.id}: {exc}"
                )
                # Continue with upload anyway
    
    # Upload the new profile photo using existing upload_logo
    url, public_id = await upload_logo(photo_data)
    user.profile_photo_url = url
    
    session.add(user)
    await session.commit()
    await session.refresh(user)
    
    logger.info(f"Updated profile photo for user {user.id}: {public_id}")
    
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
                    f"Failed to delete profile photo from Cloudinary for user {user_id}: {exc}"
                )
                # Continue with user deletion even if Cloudinary fails
        else:
            logger.warning(f"Could not extract public_id from URL: {user.profile_photo_url}")
    
    # Delete the user record from the database
    stmt = delete(User).where(User.id == user_id)
    await session.execute(stmt)
    await session.commit()
    
    logger.info(f"Deleted user profile: {user_id}")
