import logging
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError

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
from app.core.ip import get_client_ip
from app.core.rate_limit import limiter
from app.core.token import (
    create_access_token,
    create_refresh_token,
    hash_token,
)
from app.dependencies import CurrentUser, DBSession, RedisClient
from app.models.auth import RefreshToken
from app.models.users import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    LoginUserResponse,
    LogoutAllResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SessionListResponse,
    SignupRequest,
    UserResponse,
    VerifyEmailRequest,
)
from app.schemas.response import ErrorResponse, SuccessResponse
from app.services.auth import (
    _resolve_current_family_id,
    authenticate_with_google,
    build_google_auth_url,
    list_user_sessions,
    logout_session,
    refresh_session,
    request_password_reset,
    resend_verification_email,
    reset_password,
    revoke_all_user_sessions,
    set_access_cookie,
    set_refresh_cookie,
    signin,
    signup,
)
from app.services.email import send_onboarding_email

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/me",
    response_model=SuccessResponse[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated organiser profile",
    responses={
        200: {"description": "Profile retrieved successfully"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
@limiter.limit("5/minute")
async def get_current_user_profile(
    request: Request,
    current_user: CurrentUser,
) -> SuccessResponse[UserResponse]:
    """Retrieves the profile information of the currently authenticated organizer.

    Requires a valid user session, rejecting unauthenticated requests with a 401
    Unauthorized error. Because the profile data is already fetched by the `CurrentUser`
    dependency, this handler introduces minimal overhead and is rate-limited to 5
    requests per minute per client IP.
    """
    return SuccessResponse(
        message="Profile retrieved successfully",
        data=UserResponse.model_validate(current_user),
    )


@router.post(
    "/signup",
    response_model=SuccessResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new organiser account",
    description=(
        "Registers a new user account with an email and password. "
        "Validates the password strength, hashes it, and stores the user. "
        "Generates and dispatches a verification token via email."
    ),
    responses={
        201: {
            "description": "Successful Registration",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": (
                            "Registration successful. Please check your email "
                            "to verify your account."
                        ),
                        "data": {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "name": "Jane Doe",
                            "email": "jane@example.com",
                            "is_email_verified": False,
                            "profile_photo_url": None,
                            "created_at": "2026-05-09T05:28:33Z",
                            "updated_at": "2026-05-09T05:28:33Z",
                        },
                    }
                }
            },
        },
        409: {
            "model": ErrorResponse,
            "description": (
                "Unable to create account. Please use a different email or login."
            ),
        },
        422: {"model": ErrorResponse, "description": "Validation error in the payload"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
@limiter.limit("10/minute")
async def register(
    request: Request,
    payload: SignupRequest,
    session: DBSession,
    redis: RedisClient,
) -> Any:
    """Registers a new organiser account.

    Validates password strength, hashes it, saves the user to the database, creates a
    verification token in Redis, and dispatches a verification email. This public
    endpoint performs CPU-intensive password hashing, executes write operations to both
    the database and Redis, and initiates an outgoing SMTP request under a rate limit of
    10 requests per minute per client IP.
    """
    try:
        user, email_sent = await signup(session, redis, payload)
        if email_sent:
            message = (
                "Registration successful. "
                "Please check your email to verify your account."
            )
        else:
            message = (
                "Account created. Verification email failed to send. "
                "Please request a new one."
            )
    except EmailConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to create account. Please use a different email or login.",
        ) from exc

    return SuccessResponse(
        message=message,
        data=UserResponse.model_validate(user),
    )


@router.post(
    "/resend-verification-email",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Resend account verification email",
    description=(
        "Resends the account verification email if the user exists and has not "
        "yet verified their email address. Always returns a uniform 200 to "
        "prevent account enumeration."
    ),
    responses={
        200: {
            "description": "Request accepted",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": (
                            "If your email is registered and unverified, "
                            "a new verification email has been sent."
                        ),
                        "data": None,
                    }
                }
            },
        },
        400: {
            "model": ErrorResponse,
            "description": "Email is already verified",
        },
        422: {
            "model": ErrorResponse,
            "description": "Validation error in the payload",
        },
        429: {
            "model": ErrorResponse,
            "description": "Rate limit exceeded",
        },
    },
)
@limiter.limit("3/minute")
async def resend_verification(
    request: Request,
    payload: ResendVerificationRequest,
    session: DBSession,
    redis: RedisClient,
) -> Any:
    """Resends the email verification link to an unverified user's email address.

    Queries the database for the user status, generates and writes a verification token
    to Redis, and dispatches an SMTP email request. This public endpoint returns a
    generic success message to prevent user enumeration and is rate-limited to 3
    requests per minute per client IP.
    """
    try:
        await resend_verification_email(session, redis, payload)
    except EmailAlreadyVerifiedError as exc:
        logger.info(
            "Resend-verification skipped: %s is already verified",
            hash_token(payload.email),
            exc_info=exc,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified.",
        ) from exc
    except EmailDeliveryError as exc:
        logger.warning(
            "Resend-verification email delivery failed for %s",
            hash_token(payload.email),
            exc_info=exc,
        )

    return SuccessResponse(
        message=(
            "If your email is registered and unverified, "
            "a new verification email has been sent."
        ),
        data=None,
    )


@router.post(
    "/reset-password",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Reset Organizer Password",
    responses={
        200: {
            "description": "Password reset successful",
        },
        400: {
            "model": ErrorResponse,
            "description": "Token is invalid or expired",
        },
        422: {
            "model": ErrorResponse,
            "description": "Validation error in the payload",
        },
        429: {
            "model": ErrorResponse,
            "description": "Too many requests",
        },
    },
)
@limiter.limit("5/minute")
async def reset_organizer_password(
    request: Request,
    payload: ResetPasswordRequest,
    session: DBSession,
    redis: RedisClient,
) -> SuccessResponse[None]:
    """Resets the password for an organiser using a valid reset token.

    Validates the token against Redis, hashes the new password using a CPU-intensive
    function, updates the user record in the database, and deletes the token. This
    token-authorized endpoint is rate-limited to 5 requests per minute per client IP.
    """
    try:
        await reset_password(session, redis, payload)
    except InvalidPasswordResetTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="token is invalid or expired",
        ) from exc

    return SuccessResponse(
        message="Password reset successful. Please proceed to login.",
        data=None,
    )


@router.post(
    "/login",
    response_model=SuccessResponse[LoginResponse],
    status_code=status.HTTP_200_OK,
    summary="Login an existing user",
    description=(
        "Validates email and password against users table. "
        "Returns generic 401 'Invalid credentials' for wrong email OR wrong password. "
        "Returns 403 if email not verified. "
        "Sets access token and 7 day refresh token as httpOnly cookies. "
        "Prevents no more than 5 failed login attempts in 15 mins."
    ),
    responses={
        200: {
            "description": "Successful Login",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Login successful",
                        "data": {
                            "user": {
                                "id": "123e4567-e89b-12d3-a456-426614174000",
                                "name": "Jane Doe",
                                "email": "jane@example.com",
                                "is_email_verified": True,
                                "profile_photo_url": None,
                                "created_at": "2026-05-09T05:28:33Z",
                                "updated_at": "2026-05-09T05:28:33Z",
                            },
                        },
                    }
                }
            },
        },
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
        403: {"model": ErrorResponse, "description": "Email not verified"},
        422: {"model": ErrorResponse, "description": "Validation error in the payload"},
        423: {"model": ErrorResponse, "description": "Too many failed attempts"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
@limiter.limit("10/minute")
async def login(
    request: Request,
    payload: LoginRequest,
    session: DBSession,
    redis: RedisClient,
    response: Response,
) -> SuccessResponse[LoginResponse]:
    """Authenticates an organiser and establishes a new login session.

    Verifies credentials, checks and increments failure limits in Redis, writes a new
    session row to the database, and issues HttpOnly access and refresh cookies. This
    public endpoint features CPU-intensive password hashing and is limited to 10
    requests per minute per IP, locking accounts after 5 consecutive failures.
    """
    try:
        user, access_token, refresh_token = await signin(
            session, redis, payload, request
        )

    except EmailNotVerifiedError as unverified_exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email",
        ) from unverified_exc

    except InvalidCredentialsError as invalid_exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        ) from invalid_exc

    except AccountLockedError as locked_exc:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=str(locked_exc) or "Too many failed login attempts.",
        ) from locked_exc

    set_access_cookie(response, access_token)
    set_refresh_cookie(response, refresh_token)

    return SuccessResponse(
        message="Login successful",
        data=LoginResponse(
            user=LoginUserResponse(
                first_name=user.first_name,
                last_name=user.last_name,
                email=user.email,
                is_email_verified=user.is_email_verified,
            ),
        ),
    )


@router.post(
    "/refresh",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description=(
        "Issues a new access token and rotates the refresh token. "
        "Requires a valid refresh token cookie. "
        "The new tokens are delivered as HttpOnly cookies."
    ),
    responses={
        200: {
            "description": "Token refreshed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Token refreshed",
                        "data": None,
                    }
                }
            },
        },
        401: {
            "model": ErrorResponse,
            "description": "Invalid, expired, or missing refresh token",
        },
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
@limiter.limit("10/minute")
async def refresh(
    request: Request,
    response: Response,
    session: DBSession,
    redis: RedisClient,
) -> SuccessResponse[None]:
    """Rotates and issues a new set of access and refresh tokens.

    Validates the client's current refresh token cookie, updates the session record in
    the database, and returns rotated HttpOnly cookies. This cookie-authorized endpoint
    requires a database query and update write, and is rate-limited to 10 requests per
    minute per IP.
    """
    refresh_token = request.cookies.get(settings.REFRESH_COOKIE)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )

    access_token = request.cookies.get(settings.ACCESS_COOKIE)

    try:
        new_access, new_refresh = await refresh_session(
            session, redis, refresh_token, access_token, request
        )
    except InvalidRefreshTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from exc

    set_access_cookie(response, new_access)
    set_refresh_cookie(response, new_refresh)

    return SuccessResponse(
        message="Token refreshed",
        data=None,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout user",
    description=(
        "Logs out the current user by invalidating their tokens. "
        "Clears the access and refresh HttpOnly cookies from the browser."
    ),
    responses={
        204: {"description": "Logout successful (no content)"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
@limiter.limit("10/minute")
async def logout(
    request: Request,
    response: Response,
    session: DBSession,
    redis: RedisClient,
) -> None:
    """Logs out the current organiser by invalidating their active session.

    Marks the active refresh token as revoked in the database and deletes browser
    cookies. This endpoint requires valid session cookies, performs a single database
    update operation, and is rate-limited to 10 requests per minute per IP.
    """
    refresh_token = request.cookies.get(settings.REFRESH_COOKIE)
    access_token = request.cookies.get(settings.ACCESS_COOKIE)

    await logout_session(session, redis, refresh_token, access_token)

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


@router.post(
    "/forgot-password",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Request a password reset email",
    description=(
        "Initiates the password reset process by generating a reset token and "
        "dispatching it via email."
    ),
    responses={
        200: {
            "description": "Password reset email sent (if the email is registered)",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": (
                            "If an account with that email exists, a password reset "
                            "email has been sent."
                        ),
                        "data": None,
                    }
                }
            },
        },
        422: {"model": ErrorResponse, "description": "Validation error in the payload"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
@limiter.limit("3/minute")
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    session: DBSession,
    redis: RedisClient,
) -> Any:
    """Requests a password reset link email.

    Checks database for email existence, generates a secure reset token, writes it to
    Redis with a time-to-live parameter, and sends a reset link via a blocking SMTP
    network request. This public endpoint returns a generic success response to prevent
    account enumeration and is rate-limited to 3 requests per minute per client IP.
    """
    try:
        await request_password_reset(session, redis, payload)
    except EmailDeliveryError as exc:
        logger.warning(
            "Password reset email delivery failed for %s",
            hash_token(payload.email),
            exc_info=exc,
        )

    return SuccessResponse(
        message=(
            "If an account with that email exists, "
            "a password reset email has been sent."
        ),
        data=None,
    )


@router.post(
    "/verify-email",
    response_model=SuccessResponse[dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="Verify email token",
    responses={
        200: {"description": "Email verified successfully"},
        400: {"model": ErrorResponse, "description": "User already verified"},
        401: {"model": ErrorResponse, "description": "Token expired or invalid"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
@limiter.limit("10/minute")
async def verify_email(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    session: DBSession,
    redis: RedisClient,
    payload: VerifyEmailRequest,
) -> Any:
    """Verifies a user's email address using a verification token.

    Performs a Redis GETDEL query to read and remove the token, checks the user in the
    database, marks them verified, creates a new login session, and schedules an
    onboarding background task. This token-based endpoint requires multiple database
    writes and is rate-limited to 10 requests per minute per IP.
    """
    token_hash = hash_token(payload.token)
    token_key = f"verify:{token_hash}"
    user_id = await redis.getdel(token_key)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please request a new verification email",
        )

    user = await session.get(User, user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please request a new verification email",
        )

    if user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already verified",
        )

    user.is_email_verified = True
    session.add(user)

    access_token = create_access_token(user.id)
    raw_refresh_token, expire = create_refresh_token(user.id)

    now = datetime.now(UTC)
    refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh_token),
        expires_at=expire,
        family_id=uuid.uuid4(),
        user_agent=(request.headers.get("user-agent", "")[:1000] or None),
        ip_address=get_client_ip(request),
        last_used_at=now,
    )
    session.add(refresh_token)

    try:
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database update failed, please try again",
        ) from None

    background_tasks.add_task(send_onboarding_email, user.email)

    set_access_cookie(response, access_token)
    set_refresh_cookie(response, raw_refresh_token)

    return SuccessResponse(message="Email verified", data={"next": "onboarding"})


@router.get(
    "/google",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    summary="Start Google OAuth",
    description="Redirects the user to Google's OAuth consent screen.",
    responses={
        307: {"description": "Redirect to Google OAuth consent screen"},
    },
)
@limiter.limit("10/minute")
async def google_login(request: Request, redis: RedisClient) -> RedirectResponse:
    """Starts the Google OAuth login or signup flow.

    Generates the Google authentication URL redirect target with state parameters and
    saves the state token to Redis to prevent cross-site request forgery attacks. This
    public endpoint is rate-limited to 10 requests per minute per IP.
    """
    auth_url = await build_google_auth_url(redis)
    return RedirectResponse(
        url=auth_url,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )


@router.get(
    "/google/callback",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    summary="Handle Google OAuth callback",
    description=(
        "Exchanges the Google authorization code for user information, "
        "creates or signs in the corresponding Flare Tag account, "
        "then redirects the browser to the frontend. Successful authentication "
        "redirects to the frontend onboarding placeholder page, while OAuth "
        "failures redirect to the frontend login page with an error message."
    ),
    responses={
        307: {
            "description": "Browser redirected to the frontend success or error page",
            "headers": {
                "Location": {
                    "description": (
                        "Frontend URL used to continue the OAuth flow. "
                        "Success redirects to FRONTEND_URL/coming-soon and "
                        "errors redirect to FRONTEND_URL/login?error=..."
                    ),
                    "schema": {"type": "string"},
                }
            },
        },
    },
)
@limiter.limit("10/minute")
async def google_callback(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    session: DBSession,
    redis: RedisClient,
    code: str = Query(..., description="Google authorization code"),
    state: str = Query(..., description="OAuth state used to prevent CSRF"),
) -> RedirectResponse:
    """Handles the redirect callback from the Google OAuth service.

    Exchanges the authorization code for user details, creating or retrieving the user
    record, writing a new session to the database, and redirecting the user to the
    frontend dashboard or onboarding. This callback blocks on external network calls to
    Google's token endpoint and is rate-limited to 10 requests per minute per IP.
    """
    try:
        user, is_new_user = await authenticate_with_google(session, redis, code, state)
    except GoogleOAuthError as exc:
        error_query = urlencode({"error": exc.message})
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/login?{error_query}",
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )

    access_token = create_access_token(user.id)
    raw_refresh_token, expire = create_refresh_token(user.id)

    now = datetime.now(UTC)
    refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh_token),
        expires_at=expire,
        family_id=uuid.uuid4(),
        user_agent=(request.headers.get("user-agent", "")[:1000] or None),
        ip_address=get_client_ip(request),
        last_used_at=now,
    )
    session.add(refresh_token)
    await session.commit()

    if is_new_user:
        background_tasks.add_task(send_onboarding_email, user.email)

    redirect = RedirectResponse(
        url=f"{settings.FRONTEND_URL}/dashboard",
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )

    set_access_cookie(redirect, access_token)
    set_refresh_cookie(redirect, raw_refresh_token)

    return redirect


@router.get(
    "/sessions",
    response_model=SuccessResponse[SessionListResponse],
    status_code=status.HTTP_200_OK,
    summary="List active sessions",
    description=(
        "Returns all active (non-revoked, non-expired) sessions for the "
        "current user. The is_current field identifies the session "
        "associated with the refresh token cookie on this request."
    ),
    responses={
        200: {"description": "Active sessions retrieved."},
        401: {"model": ErrorResponse, "description": "Not authenticated."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("10/minute")
async def list_sessions(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> SuccessResponse[SessionListResponse]:
    """Lists active sessions for the current authenticated user.

    Queries the database refresh tokens table filtered by user ID, utilizing offset and
    limit pagination, and identifies which session matches the caller's request cookies.
    This endpoint requires an active authenticated user session and is rate-limited to
    10 requests per minute per IP.
    """
    raw_refresh = request.cookies.get(settings.REFRESH_COOKIE)
    current_family_id = await _resolve_current_family_id(session, raw_refresh)

    data = await list_user_sessions(
        session=session,
        user_id=current_user.id,
        current_family_id=current_family_id,
        page=page,
        limit=limit,
    )

    return SuccessResponse(
        message="Active sessions retrieved.",
        data=data,
    )


@router.post(
    "/logout/all",
    response_model=SuccessResponse[LogoutAllResponse],
    status_code=status.HTTP_200_OK,
    summary="Logout all sessions",
    description=(
        "Revokes every active session for the current user across all devices. "
        "Also blacklists the current access token."
    ),
    responses={
        200: {"description": "All sessions terminated."},
        401: {"model": ErrorResponse, "description": "Not authenticated."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("5/minute")
async def logout_all(
    request: Request,
    response: Response,
    session: DBSession,
    redis: RedisClient,
    current_user: CurrentUser,
) -> SuccessResponse[LogoutAllResponse]:
    """Revokes all active sessions and tokens for the user across all devices.

    Bulk deletes all user refresh tokens from the database, writes the current access
    token's JTI to the Redis blacklist with a TTL, and deletes the browser cookies. This
    endpoint requires an active user session and is rate-limited to 5 requests per
    minute per IP.
    """
    access_token = request.cookies.get(settings.ACCESS_COOKIE)

    count = await revoke_all_user_sessions(
        session=session,
        redis=redis,
        user_id=current_user.id,
        access_token=access_token,
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

    return SuccessResponse(
        message="All sessions have been terminated.",
        data=LogoutAllResponse(sessions_revoked=count),
    )
