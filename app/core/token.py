import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from jose import jwt
from redis.asyncio import Redis

from app.core.config import settings


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_token() -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_token(raw_token)
    return raw_token, token_hash


async def blacklist_token(redis: Redis, jti: str, remaining_seconds: int) -> None:
    if remaining_seconds > 0:
        await redis.set(f"{settings.BLACKLIST_PREFIX}{jti}", "1", ex=remaining_seconds)


async def is_token_blacklisted(redis: Redis, jti: str) -> bool:
    exists = await redis.exists(f"{settings.BLACKLIST_PREFIX}{jti}")
    return bool(exists)


async def store_verification_token(
    redis: Redis,
    token_hash: str,
    user_id: str,
) -> None:
    ttl_seconds = settings.VERIFICATION_TOKEN_TTL_MINUTES * 60
    await redis.set(f"{settings.TOKEN_PREFIX}{token_hash}", user_id, ex=ttl_seconds)


async def get_verified_user_id(
    redis: Redis,
    token_hash: str,
) -> str | None:
    key = f"{settings.TOKEN_PREFIX}{token_hash}"
    user_id = await redis.get(key)
    if user_id is not None:
        await redis.delete(key)
        return str(user_id)
    return None


def create_access_token(user_id: UUID) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": secrets.token_hex(16),
    }
    return str(jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM))


def create_refresh_token(user_id: UUID) -> tuple[str, datetime]:
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
    ttl_seconds = settings.PASSWORD_RESET_TOKEN_TTL_MINUTES * 60
    await redis.set(
        f"{settings.PASSWORD_RESET_PREFIX}{token_hash}", user_id, ex=ttl_seconds
    )


async def get_password_reset_user_id(
    redis: Redis,
    token_hash: str,
) -> str | None:
    key = f"{settings.PASSWORD_RESET_PREFIX}{token_hash}"
    user_id = await redis.getdel(key)
    if user_id is not None:
        return str(user_id)
    return None


async def store_google_oauth_state(redis: Redis, state: str) -> None:
    """Stores a Google OAuth state parameter for CSRF protection."""
    ttl_seconds = settings.GOOGLE_OAUTH_STATE_TTL_MINUTES * 60
    await redis.set(f"{settings.GOOGLE_STATE_PREFIX}{state}", "1", ex=ttl_seconds)


async def get_google_oauth_state(redis: Redis, state: str) -> bool:
    """Verifies and consumes a Google OAuth state parameter."""
    key = f"{settings.GOOGLE_STATE_PREFIX}{state}"
    stored = await redis.getdel(key)
    if stored is None:
        return False

    return True


async def store_google_exchange_code(
    redis: Redis,
    code_hash: str,
    user_id: str,
) -> None:
    """Stores a short-lived Google exchange code for finalising authentication."""
    await redis.set(f"{settings.GOOGLE_EXCHANGE_PREFIX}{code_hash}", user_id, ex=60)


async def get_google_exchange_user_id(
    redis: Redis,
    code_hash: str,
) -> str | None:
    """Retrieves and consumes a Google exchange code."""
    key = f"{settings.GOOGLE_EXCHANGE_PREFIX}{code_hash}"
    user_id = await redis.getdel(key)
    return str(user_id) if user_id else None
