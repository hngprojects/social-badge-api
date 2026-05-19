import asyncio
import base64
import binascii
import json
import logging
import uuid
from datetime import UTC, datetime
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import Request, Response
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    AccountLockedError,
    EmailAlreadyVerifiedError,
    EmailConflictError,
    EmailDeliveryError,
    EmailNotVerifiedError,
    GoogleOAuthError,
    InvalidCredentialsError,
    InvalidPasswordResetTokenError,
    InvalidRefreshTokenError,
)
from app.core.ip import get_client_ip, mask_ip
from app.core.security import hash_password, verify_password
from app.core.token import (
    blacklist_token,
    create_access_token,
    create_refresh_token,
    generate_token,
    get_google_exchange_user_id,
    get_google_oauth_state,
    get_password_reset_user_id,
    hash_token,
    store_google_exchange_code,
    store_google_oauth_state,
    store_password_reset_token,
    store_verification_token,
)
from app.models import AuthProvider, RefreshToken, User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SessionListResponse,
    SessionResponse,
    SignupRequest,
)
from app.services.email import (
    send_account_lock_email,
    send_password_reset_email,
    send_security_alert_email,
    send_verification_email,
)

logger = logging.getLogger(__name__)

GOOGLE_SCOPES = ("openid", "email", "profile")

# Stable dummy hash used to equalize CPU cost between known/unknown users
# and prevent timing-based account enumeration.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-equalization")


async def signup(
    session: AsyncSession,
    redis: Redis,
    payload: SignupRequest,
) -> tuple[User, bool]:
    existing = await session.execute(select(User).where(User.email == payload.email))
    if existing.scalars().first() is not None:
        raise EmailConflictError

    password_hash = await asyncio.to_thread(hash_password, payload.password)

    user = User(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        password_hash=password_hash,
    )
    session.add(user)

    try:
        await session.flush()
    except IntegrityError as err:
        await session.rollback()
        raise EmailConflictError from err

    auth_provider = AuthProvider(
        provider="email",
        user_id=user.id,
        label="Email and Password",
    )
    session.add(auth_provider)

    raw_token, token_hash = generate_token()
    await store_verification_token(redis, token_hash, str(user.id))

    await session.commit()

    email_sent = True
    try:
        await send_verification_email(payload.email, raw_token)
    except EmailDeliveryError:
        email_sent = False

    return user, email_sent


async def resend_verification_email(
    session: AsyncSession,
    redis: Redis,
    payload: ResendVerificationRequest,
) -> None:
    result = await session.execute(select(User).where(User.email == payload.email))
    user = result.scalars().first()

    if not user:
        return

    if user.is_email_verified:
        raise EmailAlreadyVerifiedError

    raw_token, token_hash = generate_token()
    await store_verification_token(redis, token_hash, str(user.id))

    await send_verification_email(user.email, raw_token)


async def reset_password(
    session: AsyncSession,
    redis: Redis,
    payload: ResetPasswordRequest,
) -> None:
    token_hash = hash_token(payload.token)
    user_id = await get_password_reset_user_id(redis, token_hash)

    if user_id is None:
        raise InvalidPasswordResetTokenError

    try:
        parsed_user_id = UUID(user_id)
    except ValueError as exc:
        raise InvalidPasswordResetTokenError from exc

    result = await session.execute(select(User).where(User.id == parsed_user_id))
    user = result.scalars().first()

    if user is None:
        raise InvalidPasswordResetTokenError

    user.password_hash = await asyncio.to_thread(hash_password, payload.new_password)
    await session.execute(
        delete(RefreshToken).where(RefreshToken.user_id == parsed_user_id)
    )
    await session.flush()
    await session.refresh(user)
    await session.commit()


async def signin(
    session: AsyncSession,
    redis: Redis,
    payload: LoginRequest,
    request: Request | None = None,
) -> tuple[User, str, str]:
    await check_lockout(redis, payload.email)

    existing = await session.execute(select(User).where(User.email == payload.email))
    existing_user = existing.scalars().first()
    if not existing_user:
        # Equalize timing with the wrong-password branch to avoid leaking
        # whether the email is registered.
        await asyncio.to_thread(verify_password, payload.password, _DUMMY_PASSWORD_HASH)
        attempts = await increment_failed_attempts(redis, payload.email)

        if attempts >= settings.MAX_LOGIN_ATTEMPTS:
            raise AccountLockedError("Account locked due to too many failed attempts.")

        raise InvalidCredentialsError

    if not existing_user.password_hash or not await asyncio.to_thread(
        verify_password, payload.password, existing_user.password_hash
    ):
        attempts = await increment_failed_attempts(redis, payload.email)

        if attempts >= settings.MAX_LOGIN_ATTEMPTS:
            try:
                await send_account_lock_email(existing_user.email)
            except EmailDeliveryError:
                pass
            raise AccountLockedError("Account locked due to too many failed attempts.")

        raise InvalidCredentialsError

    await reset_attempts(redis, payload.email)

    if not existing_user.is_email_verified:
        raise EmailNotVerifiedError

    access_token = create_access_token(existing_user.id)
    raw_refresh_token, expire = create_refresh_token(existing_user.id)

    family_id = uuid.uuid4()
    now = datetime.now(UTC)

    refresh_token = RefreshToken(
        user_id=existing_user.id,
        token_hash=hash_token(raw_refresh_token),
        expires_at=expire,
        family_id=family_id,
        user_agent=(
            (request.headers.get("user-agent", "")[:1000] or None) if request else None
        ),
        ip_address=get_client_ip(request) if request else None,
        last_used_at=now,
    )
    session.add(refresh_token)

    await session.commit()

    return existing_user, access_token, raw_refresh_token


async def _blacklist_access_token_if_valid(
    redis: Redis, access_token: str | None
) -> None:
    if not access_token:
        return
    try:
        payload = await asyncio.to_thread(
            jwt.decode,
            access_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": False},
        )
    except JWTError:
        return

    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        return

    remaining = int(exp) - int(datetime.now(UTC).timestamp())
    if remaining > 0:
        await blacklist_token(redis, jti, remaining)


async def _send_security_alert_best_effort(email: str, detected_at: datetime) -> None:
    try:
        await send_security_alert_email(email, detected_at)
    except Exception:
        logger.exception(
            "Security alert failed to deliver to %s — revocation complete",
            email,
        )


async def refresh_session(
    session: AsyncSession,
    redis: Redis,
    raw_refresh_token: str,
    access_token: str | None,
    request: Request | None = None,
) -> tuple[str, str]:
    token_hash_str = await asyncio.to_thread(hash_token, raw_refresh_token)

    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash_str)
    )
    token_obj = result.scalars().first()

    if not token_obj:
        raise InvalidRefreshTokenError

    now = datetime.now(UTC)

    if token_obj.is_revoked:
        if token_obj.last_used_at is not None:
            last_used = token_obj.last_used_at
            if last_used.tzinfo is None:
                last_used = last_used.replace(tzinfo=UTC)
            delta = (now - last_used).total_seconds()
            if delta <= settings.REFRESH_REUSE_GRACE_SECONDS:
                raise InvalidRefreshTokenError

        update_result = await session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == token_obj.family_id,
                RefreshToken.is_revoked.is_(False),
            )
            .values(is_revoked=True)
        )
        await session.commit()

        if getattr(update_result, "rowcount", 0) > 0:
            user = await session.get(User, token_obj.user_id)
            if user:
                asyncio.create_task(_send_security_alert_best_effort(user.email, now))

        logger.warning(
            "refresh_token.reuse_detected",
            extra={
                "user_id": str(token_obj.user_id),
                "family_id": str(token_obj.family_id),
            },
        )
        raise InvalidRefreshTokenError

    expires_at = token_obj.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at < now:
        raise InvalidRefreshTokenError

    user = await session.get(User, token_obj.user_id)
    if not user:
        raise InvalidRefreshTokenError

    await _blacklist_access_token_if_valid(redis, access_token)

    token_obj.is_revoked = True
    token_obj.last_used_at = now

    new_raw_refresh, new_expire = create_refresh_token(user.id)
    new_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(new_raw_refresh),
        expires_at=new_expire,
        family_id=token_obj.family_id,
        user_agent=(
            request.headers.get("user-agent", "")[:1000]
            if request
            else token_obj.user_agent
        ),
        ip_address=(get_client_ip(request) if request else token_obj.ip_address),
        last_used_at=now,
    )
    session.add(new_token)

    new_access_token = create_access_token(user.id)
    await session.commit()

    logger.info(
        "refresh_token.rotated",
        extra={
            "user_id": str(user.id),
            "family_id": str(token_obj.family_id),
        },
    )

    return new_access_token, new_raw_refresh


async def logout_session(
    session: AsyncSession,
    redis: Redis,
    raw_refresh_token: str | None,
    access_token: str | None,
) -> None:
    if raw_refresh_token:
        token_hash_str = await asyncio.to_thread(hash_token, raw_refresh_token)
        result = await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash_str)
        )
        refresh_token_obj = result.scalars().first()
        if refresh_token_obj and not refresh_token_obj.is_revoked:
            refresh_token_obj.is_revoked = True
            await session.commit()

    await _blacklist_access_token_if_valid(redis, access_token)


def _set_auth_cookie(response: Response, key: str, value: str, max_age: int) -> None:
    response.set_cookie(
        key=key,
        value=value,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=max_age,
        domain=settings.COOKIE_DOMAIN,
    )


def set_access_cookie(response: Response, access_token: str) -> None:
    _set_auth_cookie(
        response,
        key=settings.ACCESS_COOKIE,
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    _set_auth_cookie(
        response,
        key=settings.REFRESH_COOKIE,
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )


async def check_lockout(redis: Redis, identifier: str) -> None:
    key = f"{settings.FAILED_LOGIN_PREFIX}{identifier}"
    attempts = await redis.get(key)

    if attempts and int(attempts) >= settings.MAX_LOGIN_ATTEMPTS:
        ttl = await redis.ttl(key)
        minutes = max(1, ttl // 60) if ttl and ttl > 0 else 1
        raise AccountLockedError(f"Account locked. Try again in {minutes} minute(s).")


async def increment_failed_attempts(redis: Redis, identifier: str) -> int:
    key = f"{settings.FAILED_LOGIN_PREFIX}{identifier}"
    count = await redis.incr(key)

    if count == 1:
        # Set expiration only on the first failed attempt
        await redis.expire(key, settings.LOCKOUT_WINDOW)
    return int(count)


async def reset_attempts(redis: Redis, identifier: str) -> None:
    await redis.delete(f"{settings.FAILED_LOGIN_PREFIX}{identifier}")


async def request_password_reset(
    session: AsyncSession,
    redis: Redis,
    payload: ForgotPasswordRequest,
) -> None:
    """Generate a password reset token and email it to the user.

    Silently no-ops if no user exists with the given email to prevent
    email enumeration attacks. Email delivery failures are also
    swallowed silently for the same reason.
    """

    result = await session.execute(select(User).where(User.email == payload.email))
    user = result.scalars().first()

    if user is None:
        return

    raw_token, token_hash = generate_token()
    await store_password_reset_token(redis, token_hash, str(user.id))

    await send_password_reset_email(payload.email, raw_token)


async def build_google_auth_url(redis: Redis) -> str:
    """Build the Google OAuth authorisation URL and store state for CSRF protection."""

    state, _ = generate_token()
    await store_google_oauth_state(redis, state)

    params = urlencode(
        {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(GOOGLE_SCOPES),
            "state": state,
        }
    )
    return f"{settings.GOOGLE_AUTH_URL}?{params}"


async def authenticate_with_google(
    session: AsyncSession,
    redis: Redis,
    code: str,
    state: str,
) -> tuple[User, bool]:
    """
    Handles the Google OAuth callback by validating state, exchanging code for token,
    fetching user info, and upserting the user record.
    """

    state_is_valid = await get_google_oauth_state(redis, state)
    if not state_is_valid:
        raise GoogleOAuthError("Invalid or expired Google OAuth state")

    token_payload = await _exchange_google_code(code)
    user_info = await _fetch_google_user_info(token_payload["access_token"])  # type: ignore
    _validate_google_subject_consistency(
        token_payload.get("id_token"), user_info["sub"]
    )
    user, is_new_user = await _upsert_google_user(session, user_info)
    return user, is_new_user


async def _exchange_google_code(code: str) -> dict[str, str | None]:
    """
    Exchanges the authorization code for an access token
    by calling Google's token endpoint.
    """

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                settings.GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GoogleOAuthError(
                "Google token exchange failed",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise GoogleOAuthError(
                "Could not reach Google token endpoint",
                status_code=502,
            ) from exc

    payload = response.json()
    if not isinstance(payload, dict):
        raise GoogleOAuthError("Google token response was not a JSON object")
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise GoogleOAuthError("Google token response did not include an access token")
    id_token = payload.get("id_token")
    if id_token is not None and (not isinstance(id_token, str) or not id_token):
        raise GoogleOAuthError("Google token response included an invalid ID token")
    return {"access_token": access_token, "id_token": id_token}


async def _fetch_google_user_info(access_token: str) -> dict[str, str | bool | None]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                settings.GOOGLE_USER_INFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GoogleOAuthError(
                "Google user info lookup failed",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise GoogleOAuthError(
                "Could not reach Google user info endpoint",
                status_code=502,
            ) from exc

    payload = response.json()
    if not isinstance(payload, dict):
        raise GoogleOAuthError("Google user info response was not a JSON object")
    subject = payload.get("sub")
    email = payload.get("email")
    email_verified = payload.get("email_verified")
    name = payload.get("name")

    if not isinstance(subject, str) or not subject:
        raise GoogleOAuthError("Google account did not provide a stable account ID")
    if not isinstance(email, str) or not email:
        raise GoogleOAuthError("Google account did not provide an email address")
    if email_verified is not True:
        raise GoogleOAuthError("Google account email is not verified")
    if not isinstance(name, str) or not name.strip():
        raise GoogleOAuthError("Google account did not provide a valid display name")

    picture = payload.get("picture")
    picture_url = picture if isinstance(picture, str) and picture else None

    return {
        "sub": subject,
        "email": email,
        "name": name.strip(),
        "picture": picture_url,
    }


def _validate_google_subject_consistency(
    id_token: str | None, userinfo_subject: str | bool | None
) -> None:
    if id_token is None:
        return

    token_subject = _extract_google_id_token_subject(id_token)
    if token_subject != userinfo_subject:
        raise GoogleOAuthError(
            "Google token subject did not match the user info response"
        )


def _extract_google_id_token_subject(id_token: str) -> str:
    """Read the JWT payload subject for consistency checks.

    This is intentionally limited to subject extraction so we can compare
    the token endpoint identity with the userinfo identity without adding
    a separate JWT verification dependency.
    """
    segments = id_token.split(".")
    if len(segments) != 3:
        raise GoogleOAuthError("Google token response included a malformed ID token")

    payload_segment = segments[1]
    padding = "=" * (-len(payload_segment) % 4)

    try:
        payload_bytes = base64.urlsafe_b64decode(payload_segment + padding)
        payload = json.loads(payload_bytes)
    except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GoogleOAuthError(
            "Google token response included a malformed ID token"
        ) from exc

    if not isinstance(payload, dict):
        raise GoogleOAuthError("Google token response did not include a valid subject")

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise GoogleOAuthError("Google token response did not include a valid subject")
    return subject


async def _upsert_google_user(
    session: AsyncSession,
    user_info: dict[str, str | bool | None],
) -> tuple[User, bool]:
    """
    Finds or creates a User record based on Google user info,
    and ensures an AuthProvider record exists.
    """

    google_subject = str(user_info["sub"])
    email = str(user_info["email"])
    name = str(user_info["name"])
    picture = user_info["picture"]

    provider_result = await session.execute(
        select(AuthProvider).where(
            AuthProvider.provider == "google",
            AuthProvider.provider_user_id == google_subject,
        )
    )
    provider = provider_result.scalars().first()

    if provider is not None:
        user = await session.get(User, provider.user_id)
        if user is None:
            raise GoogleOAuthError("Linked Google account references a missing user")
        is_new_user = False
    else:
        existing_result = await session.execute(select(User).where(User.email == email))
        user = existing_result.scalars().first()
        is_new_user = user is None

        if user is None:
            names = name.split(maxsplit=1) if name and name.strip() else []
            if names:
                first_name = names[0]
                last_name = names[1] if len(names) > 1 else None
            else:
                first_name = email.split("@")[0]
                last_name = None

            user = User(
                first_name=first_name,
                last_name=last_name,
                email=email,
                password_hash=None,
                is_email_verified=True,
                profile_photo_url=picture if isinstance(picture, str) else None,
            )
            session.add(user)
            await session.flush()
        else:
            if user.password_hash is not None and not user.is_email_verified:
                raise GoogleOAuthError(
                    (
                        "An unverified password account already exists for this email. "
                        "Please sign in with your password and verify your email "
                        "before linking Google."
                    ),
                    status_code=409,
                )

            user.is_email_verified = True
            if isinstance(picture, str):
                user.profile_photo_url = picture

    if provider is None:
        session.add(
            AuthProvider(
                provider="google",
                provider_user_id=google_subject,
                user_id=user.id,
                label="Google",
            )
        )

    await session.commit()
    await session.refresh(user)
    return user, is_new_user


async def generate_google_exchange_token(redis: Redis, user_id: UUID) -> str:
    """Generate a one-time code for the frontend to exchange for tokens."""

    raw_code, code_hash = generate_token()
    await store_google_exchange_code(redis, code_hash, str(user_id))
    return raw_code


async def exchange_google_code_for_tokens(
    session: AsyncSession,
    redis: Redis,
    code: str,
    request: Request | None = None,
) -> tuple[User, str, str]:
    code_hash = hash_token(code)
    user_id_str = await get_google_exchange_user_id(redis, code_hash)

    if not user_id_str:
        raise GoogleOAuthError("Invalid or expired exchange code")

    user = await session.get(User, UUID(user_id_str))
    if not user:
        raise GoogleOAuthError("User not found")

    access_token = create_access_token(user.id)
    raw_refresh_token, expire = create_refresh_token(user.id)

    now = datetime.now(UTC)
    refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh_token),
        expires_at=expire,
        family_id=uuid.uuid4(),
        user_agent=(request.headers.get("user-agent", "")[:1000] if request else None),
        ip_address=(get_client_ip(request) if request else None),
        last_used_at=now,
    )
    session.add(refresh_token)
    await session.commit()

    return user, access_token, raw_refresh_token


async def list_user_sessions(
    session: AsyncSession,
    user_id: UUID,
    current_family_id: UUID | None,
    page: int = 1,
    limit: int = 20,
) -> SessionListResponse:
    """Return non-revoked, non-expired refresh token records for this user."""
    now = datetime.now(UTC)

    count_stmt = select(func.count(RefreshToken.id)).where(
        RefreshToken.user_id == user_id,
        RefreshToken.is_revoked.is_(False),
        RefreshToken.expires_at > now,
    )
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    stmt = (
        select(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked.is_(False),
            RefreshToken.expires_at > now,
        )
        .order_by(RefreshToken.last_used_at.desc().nulls_last())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()

    sessions = [
        SessionResponse(
            session_id=row.id,
            user_agent=row.user_agent,
            ip_address=mask_ip(row.ip_address),
            created_at=row.created_at,
            last_used_at=row.last_used_at,
            expires_at=row.expires_at,
            is_current=(
                row.family_id == current_family_id
                if current_family_id is not None
                else False
            ),
        )
        for row in rows
    ]

    return SessionListResponse(
        sessions=sessions,
        total=total,
        page=page,
        limit=limit,
    )


async def _resolve_current_family_id(
    session: AsyncSession,
    raw_refresh_token: str | None,
) -> UUID | None:
    """Look up the family_id for the current refresh cookie, if present."""
    if not raw_refresh_token:
        return None
    token_hash_str = await asyncio.to_thread(hash_token, raw_refresh_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash_str)
    )
    row = result.scalars().first()
    return row.family_id if row else None


async def revoke_all_user_sessions(
    session: AsyncSession,
    redis: Redis,
    user_id: UUID,
    access_token: str | None,
) -> int:
    """Revoke every active session for this user."""
    result = await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked.is_(False),
        )
        .values(is_revoked=True)
        .returning(RefreshToken.id)
    )
    revoked_ids = result.fetchall()
    count = len(revoked_ids)

    await session.commit()

    await _blacklist_access_token_if_valid(redis, access_token)

    logger.info(
        "logout_all.sessions_revoked",
        extra={"user_id": str(user_id), "count": count},
    )

    return count
