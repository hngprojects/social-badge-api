import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import PostgresDsn, RedisDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings and configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "flare-tag-be"
    ENVIRONMENT: str = "local"
    API_V1_PREFIX: str = "/api/v1"
    FRONTEND_URL: str = "http://localhost:3000"
    APP_DOMAIN: str = "social-badge.hng14.com"
    ALLOWED_ORIGINS: list[str] | str = []

    DATABASE_URL: PostgresDsn
    REDIS_URL: RedisDsn | str = "redis://localhost:6379/0"

    SECRET_KEY: str
    ALGORITHM: Literal["HS256", "HS384", "HS512"] = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    VERIFICATION_TOKEN_TTL_MINUTES: int = 30
    PASSWORD_RESET_TOKEN_TTL_MINUTES: int = 30

    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    ACCESS_COOKIE: str = "access_token"
    REFRESH_COOKIE: str = "refresh_token"
    COOKIE_DOMAIN: str = ""

    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_WINDOW: int = 900
    FAILED_LOGIN_PREFIX: str = "failed_login:"

    CONTACT_RECIPIENT_EMAIL: str = ""
    CONTACT_NOTIFICATION_SUBJECT: str = "New Contact Form Submission — Flare Tag"
    CONTACT_CONFIRMATION_SUBJECT: str = "We received your message — Flare Tag"
    NEWSLETTER_WELCOME_SUBJECT: str = "You're subscribed to the Flare Tag newsletter!"
    VERIFICATION_SUBJECT: str = "Verify your Flare Tag account"
    ACCOUNT_LOCK_SUBJECT: str = "Your Flare Tag account has been locked"
    PASSWORD_RESET_SUBJECT: str = "Reset your Flare Tag password"  # noqa: S105
    ONBOARDING_SUBJECT: str = "Welcome to Flare Tag! Let's ship."

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"
    GOOGLE_AUTH_URL: str = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_URL: str = "https://oauth2.googleapis.com/token"  # noqa: S105
    GOOGLE_USER_INFO_URL: str = "https://www.googleapis.com/oauth2/v3/userinfo"
    GOOGLE_OAUTH_STATE_TTL_MINUTES: int = 10

    TOKEN_PREFIX: str = "verify:"  # noqa: S105
    TOKEN_USER_PREFIX: str = "verify_user:"  # noqa: S105
    PASSWORD_RESET_PREFIX: str = "pwd_reset:"  # noqa: S105
    GOOGLE_STATE_PREFIX: str = "oauth:google:state:"
    BLACKLIST_PREFIX: str = "blacklist:jti:"

    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""
    LOGO_FOLDER: str = "template-logos"

    MAX_CONTENT_BODY_SIZE: int = 10 * 1024 * 1024

    REFRESH_REUSE_GRACE_SECONDS: int = 5
    SECURITY_ALERT_SUBJECT: str = "Security alert — all sessions have been terminated"

    LOG_LEVEL: str = "INFO"
    LOG_FILE: Path = Path("logs/app.log")

    @field_validator("FRONTEND_URL", mode="after")
    @classmethod
    def clean_frontend_url(cls, val: str) -> str:
        """Cleans the frontend URL by removing trailing slashes."""
        return val.rstrip("/")

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, val: Any) -> list[str] | str:
        """Assembles the CORS origins into a list of strings."""
        if isinstance(val, str) and val.startswith("[") and val.endswith("]"):
            try:
                decoded = json.loads(val)
                if isinstance(decoded, list):
                    return decoded
            except json.JSONDecodeError:
                pass
        if isinstance(val, str) and "," in val:
            return [i.strip() for i in val.split(",")]
        elif isinstance(val, str):
            return [val.strip()]
        elif isinstance(val, list):
            return val
        raise ValueError(f"Invalid format for ALLOWED_ORIGINS: {val}")

    @model_validator(mode="after")
    def validate_cookie_policy(self) -> Settings:
        """Validates cookie configuration to ensure secure transmission rules are met.

        Raises:
            ValueError: If SameSite is set to "none" but Cookie Secure is disabled.
        """
        if self.COOKIE_SAMESITE == "none" and not self.COOKIE_SECURE:
            raise ValueError("COOKIE_SECURE must be True when COOKIE_SAMESITE='none'")
        return self

    @model_validator(mode="after")
    def validate_production_settings(self) -> Self:
        """Validates that production environment configurations do not use placeholder
        values.

        Raises:
            ValueError: If key services (Google OAuth, SMTP, contact recipient) are left
            unset or configure default placeholder values in a production environment.
        """
        if self.ENVIRONMENT.strip().lower() != "production":
            return self

        checks = {
            "GOOGLE_CLIENT_ID": (
                self.GOOGLE_CLIENT_ID,
                {"", "your_google_client_id_here"},
            ),
            "GOOGLE_CLIENT_SECRET": (
                self.GOOGLE_CLIENT_SECRET,
                {"", "your_google_client_secret_here"},
            ),
            "CONTACT_RECIPIENT_EMAIL": (
                self.CONTACT_RECIPIENT_EMAIL,
                {"", "support@yourdomain.com"},
            ),
        }
        for field, (value, banned) in checks.items():
            if value.strip() in banned:
                raise ValueError(f"{field} must be set in production")

        if (
            not self.SMTP_USER.strip()
            or not self.SMTP_PORT
            or not self.SMTP_PASSWORD.strip()
            or not self.SMTP_FROM_EMAIL.strip()
        ):
            raise ValueError(
                "SMTP host, port, credentials, and from email must be set in production"
            )

        return self

    @field_validator("MAX_CONTENT_BODY_SIZE")
    @classmethod
    def validate_max_content_body_size(cls, val: int) -> int:
        """Validates that configured max allowed request content body size is a positive
        integer."""
        if val <= 0:
            raise ValueError("MAX_CONTENT_BODY_SIZE must be greater than 0")

        return val


@lru_cache
def get_settings() -> Settings:
    """Instantiates and returns a cached Settings singleton instance.

    Uses `functools.lru_cache` to load settings from environment variables and any
    matching config files once upon first call.
    """
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
