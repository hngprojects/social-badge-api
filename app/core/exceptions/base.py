class EmailConflictError(Exception):
    """Raised when a registration attempt uses an already-registered email."""

    pass


class EmailDeliveryError(Exception):
    """Raised when an outbound email fails to deliver."""

    pass


class InvalidPasswordResetTokenError(Exception):
    """Raised when a password reset token is invalid or expired."""

    pass


class InvalidCredentialsError(Exception):
    """Raised on a failed login attempt (wrong email or password)."""

    pass


class EmailNotVerifiedError(Exception):
    """Raised when a user attempts to log in without verifying their email."""

    pass


class EmailAlreadyVerifiedError(Exception):
    """
    Raised when a resend-verification is requested for an
    already-verified email.
    """

    pass


class AccountLockedError(Exception):
    """
    Raised when a login attempt is made against a locked account (HTTP
    423).
    """

    pass


class InvalidRefreshTokenError(Exception):
    """Raised when a refresh token is invalid, expired, or revoked."""

    pass


class GoogleOAuthError(Exception):
    """Raised when a Google OAuth flow fails."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        """
        Initializes the exception - message and HTTP status code
        (400 as default).
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class PlatformTemplateNotFoundError(Exception):
    """Raised when a referenced platform template does not exist."""

    pass


class PlatformTemplateNotActiveError(Exception):
    """
    Raised when attempting to create a badge from an inactive platform
    template.
    """

    pass


class BadgeNotFoundError(Exception):
    """Raised when a referenced organiser template does not exist."""

    pass


class NotBadgeOwnerError(Exception):
    """Raised when a user attempts to act on a template they do not own."""

    pass


class BadgeAlreadyPublishedError(Exception):
    """Raised when attempting to publish an already-published template."""

    pass


class CloudinaryUploadError(Exception):
    """Raised when a Cloudinary upload or deletion fails."""

    pass


class PublicBadgeNotFoundError(Exception):
    """Raised when a public slug does not resolve to a published template."""

    pass


class BadgeRenderError(Exception):
    """
    Raised when badge rendering fails in a way that prevents any output.

        Optional asset failures (logo, participant photo) are non-fatal and
        log a
        warning instead of raising this exception.
    """

    pass
