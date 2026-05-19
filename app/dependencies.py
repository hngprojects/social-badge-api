import asyncio
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyCookie
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.token import is_token_blacklisted
from app.db.redis import get_redis_client
from app.db.session import get_session
from app.models.roles import Role, UserRole
from app.models.users import User

DBSession = Annotated[AsyncSession, Depends(get_session)]
RedisClient = Annotated[Redis, Depends(get_redis_client)]

security = APIKeyCookie(name=settings.ACCESS_COOKIE, auto_error=False)


async def get_current_user(
    session: DBSession,
    redis: RedisClient,
    token: Annotated[str | None, Depends(security)],
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        payload = await asyncio.to_thread(
            jwt.decode,
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        ) from exc

    jti = payload.get("jti")
    if not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    if await is_token_blacklisted(redis, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_admin(
    session: DBSession,
    redis: RedisClient,
    token: Annotated[str | None, Depends(security)],
) -> User:
    _forbidden = HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required",
    )
    if not token:
        raise _forbidden
    try:
        payload = await asyncio.to_thread(
            jwt.decode,
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except JWTError:
        raise _forbidden from None

    jti = payload.get("jti")
    if not jti or await is_token_blacklisted(redis, jti):
        raise _forbidden

    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise _forbidden

    user = await session.get(User, user_id)
    if user is None:
        raise _forbidden

    stmt = (
        select(Role.id)
        .join(UserRole, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user.id, Role.name == "admin")
    )
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise _forbidden

    return user


CurrentAdmin = Annotated[User, Depends(get_current_admin)]
