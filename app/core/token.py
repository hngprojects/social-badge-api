import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from jose import jwt
from redis.asyncio import Redis

from app.core.config import settings


def hash_token(token: str) -> str:
    """
    Computes a SHA-256 hash of a raw token string for secure database storage or lookup.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def generate_token() -> tuple[str, str]:
    """
    Generates a cryptographically secure random token and its SHA-256 hash.

    Returns:
        A tuple of (raw_token_string, token_sha256_hash).
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_token(raw_token)
    return raw_token, token_hash


async def blacklist_token(redis: Redis, jti: str, remaining_seconds: int) -> None:
    """
    Blacklists a JWT JTI identifier in Redis for its remaining time-to-live.

    Ensures that a logged-out or invalidated token cannot be reused
    before it naturally expires.
    """
    if remaining_seconds > 0:
        await redis.set(f"{settings.BLACKLIST_PREFIX}{jti}", "1", ex=remaining_seconds)


async def is_token_blacklisted(redis: Redis, jti: str) -> bool:
    """
    Checks whether a JWT JTI identifier is currently registered as blacklisted in Redis.
    """
    exists = await redis.exists(f"{settings.BLACKLIST_PREFIX}{jti}")
    return bool(exists)


async def store_verification_token(
    redis: Redis,
    token_hash: str,
    user_id: str,
) -> None:
    """
    Stores the verification token hash mapped to the user ID in Redis.

    Creates both a token-to-user-id mapping and a user-id-to-token-hash index mapping,
    both expiring according to `VERIFICATION_TOKEN_TTL_MINUTES`.
    """
    ttl_seconds = settings.VERIFICATION_TOKEN_TTL_MINUTES * 60
    await redis.set(f"{settings.TOKEN_PREFIX}{token_hash}", user_id, ex=ttl_seconds)
    await redis.set(
        f"{settings.TOKEN_USER_PREFIX}{user_id}", token_hash, ex=ttl_seconds
    )


async def get_verified_user_id(
    redis: Redis,
    token_hash: str,
) -> str | None:
    """
    Retrieves and deletes (consumes) user ID associated with a verification token hash
    in Redis.

    Also deletes the corresponding reverse index mapping key.
    """
    key = f"{settings.TOKEN_PREFIX}{token_hash}"
    user_id = await redis.getdel(key)
    if user_id:
        decoded = user_id.decode() if isinstance(user_id, bytes) else str(user_id)
        await redis.delete(f"{settings.TOKEN_USER_PREFIX}{decoded}")
        return decoded
    return None


def create_access_token(user_id: UUID) -> str:
    """
    Creates a JWT access token for a user with configured expiration time
    and a unique JTI.
    """
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": secrets.token_hex(16),
    }
    return str(jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM))


def create_refresh_token(user_id: UUID) -> tuple[str, datetime]:
    """
    Creates a JWT refresh token for a user with the configured expiration days.

    Returns:
        A tuple containing (encoded_refresh_jwt_token, expiration_datetime).
    """
    expire = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(UTC),
        "type": "refresh",
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(
        payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    ), expire


async def store_password_reset_token(
    redis: Redis,
    token_hash: str,
    user_id: str,
) -> None:
    """
    Stores the password reset token hash mapped to user ID in Redis with
    a short-lived TTL.
    """
    ttl_seconds = settings.PASSWORD_RESET_TOKEN_TTL_MINUTES * 60
    await redis.set(
        f"{settings.PASSWORD_RESET_PREFIX}{token_hash}", user_id, ex=ttl_seconds
    )


async def get_password_reset_user_id(
    redis: Redis,
    token_hash: str,
) -> str | None:
    """
    Retrieves and deletes (consumes) user ID associated with a password reset token hash
    in Redis.
    """
    key = f"{settings.PASSWORD_RESET_PREFIX}{token_hash}"
    user_id = await redis.getdel(key)
    if user_id is not None:
        return str(user_id)
    return None


async def store_google_oauth_state(redis: Redis, state: str) -> None:
    """
    Stores a Google OAuth state parameter in Redis with a short-lived TTL
    to prevent CSRF attacks.
    """
    ttl_seconds = settings.GOOGLE_OAUTH_STATE_TTL_MINUTES * 60
    await redis.set(f"{settings.GOOGLE_STATE_PREFIX}{state}", "1", ex=ttl_seconds)


async def get_google_oauth_state(redis: Redis, state: str) -> bool:
    """
    Verifies and consumes (deletes) a Google OAuth state parameter from Redis.
    """
    key = f"{settings.GOOGLE_STATE_PREFIX}{state}"
    stored = await redis.getdel(key)
    if stored is None:
        return False

    return True



async def revoke_previous_verification_token(
    redis: Redis,
    user_id: str,
) -> None:
    """
    Finds and deletes any active verification token associated with a given user ID
    in Redis.
    """
    user_index_key = f"{settings.TOKEN_USER_PREFIX}{user_id}"
    old_hash = await redis.get(user_index_key)
    if old_hash:
        if isinstance(old_hash, bytes):
            old_hash = old_hash.decode()
        await redis.delete(f"{settings.TOKEN_PREFIX}{old_hash}")
        await redis.delete(user_index_key)
