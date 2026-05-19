import logging
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
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
    ResendVerificationRequest,
    ResetPasswordRequest,
    SignupRequest,
    UserResponse,
    VerifyEmailRequest,
)
from app.schemas.response import ErrorResponse, SuccessResponse
from app.services.auth import (
    authenticate_with_google,
    build_google_auth_url,
    logout_session,
    refresh_session,
    request_password_reset,
    resend_verification_email,
    reset_password,
    set_access_cookie,
    set_refresh_cookie,
    signin,
    signup,
)

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
@limiter.limit("5/minute")
async def resend_verification(
    request: Request,
    payload: ResendVerificationRequest,
    session: DBSession,
    redis: RedisClient,
) -> Any:
    try:
        await resend_verification_email(session, redis, payload)
    except EmailAlreadyVerifiedError as exc:
        logger.info(
            "Resend-verification skipped: %s is already verified",
            hash_token(payload.email),
            exc_info=exc,
        )
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
    """Reset a user's password using a valid password reset token."""
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
@limiter.limit("20/minute")
async def login(
    request: Request,
    payload: LoginRequest,
    session: DBSession,
    redis: RedisClient,
    response: Response,
) -> SuccessResponse[LoginResponse]:
    try:
        user, access_token, refresh_token = await signin(session, redis, payload)

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
            user=UserResponse.model_validate(user),
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
    refresh_token = request.cookies.get(settings.REFRESH_COOKIE)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )

    access_token = request.cookies.get(settings.ACCESS_COOKIE)

    try:
        new_access, new_refresh = await refresh_session(
            session, redis, refresh_token, access_token
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
@limiter.limit("10/minute")
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    session: DBSession,
    redis: RedisClient,
) -> Any:
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
    session: DBSession,
    redis: RedisClient,
    payload: VerifyEmailRequest,
) -> Any:
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

    refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh_token),
        expires_at=expire,
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
    session: DBSession,
    redis: RedisClient,
    code: str = Query(..., description="Google authorization code"),
    state: str = Query(..., description="OAuth state used to prevent CSRF"),
) -> RedirectResponse:
    try:
        user, _ = await authenticate_with_google(session, redis, code, state)
    except GoogleOAuthError as exc:
        error_query = urlencode({"error": exc.message})
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/login?{error_query}",
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )

    access_token = create_access_token(user.id)
    raw_refresh_token, expire = create_refresh_token(user.id)

    refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh_token),
        expires_at=expire,
    )
    session.add(refresh_token)
    await session.commit()

    redirect = RedirectResponse(
        url=f"{settings.FRONTEND_URL}/coming-soon",
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )

    set_access_cookie(redirect, access_token)
    set_refresh_cookie(redirect, raw_refresh_token)

    return redirect
