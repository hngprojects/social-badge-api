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
    """
    Validate the caller's JWT access token and retrieve the current user.

        Purpose:
            Decodes the access token cookie, verifies that the token's JTI
            is not
            revoked (blacklisted), and fetches the associated user record
            from the database.

        Authentication Context:
            Acts as the primary authentication gate for general user
            endpoints. Requires
            the presence of the ACCESS_COOKIE API key cookie.

        Performance Implications:
            Uses Redis to query token blacklist status (fast O(1) read).
            Performs a
            primary key query on the users database table. JWT decoding is
            offloaded to
            a threadpool to avoid blocking the event loop.

        Rate Limiting:
            No native rate limiting is enforced by this dependency, but
            callers are bound
            by the rate limits of the endpoints that include it.

        Dependencies:
            Depends on `get_session` (database) and `get_redis_client`
            (Redis).
    """
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
    """
    Validate the caller's JWT access token and assert that the user has
    admin role privileges.

    Purpose:
        Verifies the access token, checks the token blacklist, retrieves the user,
        and joins the UserRole and Role tables to verify the user is associated
        with the 'admin' role.

    Authentication Context:
        Admin authorization gate. Rejects users lacking the explicit 'admin' role name
        with a 403 Forbidden.

    Performance Implications:
        Executes a database fetch for the User, followed by a join query
        between the Role and UserRole tables.
        Checks the token blacklist in Redis and decodes the JWT asynchronously.

    Rate Limiting:
        No native rate limiting is enforced by this dependency.

    Dependencies:
        Depends on `get_session` (database) and `get_redis_client` (Redis).
    """
    _forbidden = HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required",
    )
    _unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
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
        raise _unauthorized from None

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
