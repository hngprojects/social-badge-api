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
    """
    Parses a Cloudinary URL to extract the public ID of the hosted asset.

    Handles URLs with and without version segments and removes file extensions.
    """
    try:
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split("/") if p]

        try:
            upload_index = path_parts.index("upload")
            if upload_index + 1 < len(path_parts):
                parts = path_parts[upload_index + 1 :]

                if parts and parts[0].startswith("v") and parts[0][1:].isdigit():
                    parts = parts[1:]

                if not parts:
                    return None

                last_part = parts[-1]
                if "." in last_part:
                    parts[-1] = last_part.rsplit(".", 1)[0]

                public_id = "/".join(parts)
                return unquote(public_id)
        except ValueError:
            pass
    except Exception as exc:
        logger.warning(f"Failed to extract Cloudinary public_id from URL: {exc}")

    return None


async def update_profile_photo(
    session: AsyncSession,
    user: User,
    photo_data: bytes,
) -> User:
    """
    Uploads a new profile photo to Cloudinary and updates the user's database record.

    Extracts the old photo's public ID to queue it for deletion,
    uploads the new image binary to Cloudinary, commits the new URL to the database,
    and deletes the old photo on success.

    Raises:
        CloudinaryUploadError: If the upload operation fails.
    """
    old_public_id = (
        _extract_cloudinary_public_id(user.profile_photo_url)
        if user.profile_photo_url
        else None
    )

    url, public_id = await upload_logo(photo_data)
    user.profile_photo_url = url

    session.add(user)
    await session.commit()
    await session.refresh(user)

    logger.info(f"Updated profile photo for user {user.id}: {public_id}")

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
    """
    Resets the user's profile photo URL to None in the database
    and deletes the asset from Cloudinary.

    Extracts the public ID from the current photo URL, updates the database,
    commits the session, and calls Cloudinary to delete the asset.
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
    """
    Updates the user's textual profile fields (names, email, role) in the database.

    Applies any non-None updates to the user instance, commits the transaction,
    and refreshes the user.
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
    """
    Deletes a user's profile, all associated database records,
    and their Cloudinary assets.

    Collects public IDs for the user's profile photo, badge logos, and badge thumbnails.
    Deletes the User record from the database (cascading deletes where set up),
    commits, deletes all collected Cloudinary assets asynchronously,
    and invalidates the user's session tokens.
    """
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalars().first()

    public_ids_to_delete: list[str] = []

    if user and user.profile_photo_url:
        public_id = _extract_cloudinary_public_id(user.profile_photo_url)
        if public_id:
            public_ids_to_delete.append(public_id)
        else:
            logger.warning(
                "Could not extract public_id from URL: %s", user.profile_photo_url
            )

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

    delete_stmt = delete(User).where(User.id == user_id)
    await session.execute(delete_stmt)
    await session.commit()

    logger.info("Deleted user profile: %s", user_id)

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
    """
    Updates the authenticated user's password after verifying their current password.

    Validates the current password against the stored hash, hashes the new password,
    persists the change, commits, and logs out the current session
    to force re-authentication.

    Raises:
        InvalidCredentialsError: If the current password verification fails.
    """
    if not user.password_hash or not await asyncio.to_thread(
        verify_password, payload.current_password, user.password_hash
    ):
        raise InvalidCredentialsError

    user.password_hash = await asyncio.to_thread(hash_password, payload.new_password)
    session.add(user)
    await session.commit()

    await logout_session(session, redis, refresh_token, access_token)
