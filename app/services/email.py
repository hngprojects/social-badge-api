import html
import logging
from datetime import datetime
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib

from app.core.config import settings
from app.core.exceptions import EmailDeliveryError
from app.services import email_templates

logger = logging.getLogger(__name__)


class EmailProvider(Protocol):
    """Defines the abstract interface for the application's asynchronous email delivery
    service.

    Implementations must define the `send` method to dispatch messages using HTML
    content.
    """

    async def send(
        self,
        *,
        to: str | list[str],
        subject: str,
        html_content: str,
        reply_to: str | None = None,
    ) -> None:
        """Asynchronously dispatches an email message with HTML payload.

        Raises:
            EmailDeliveryError: If connection or transmission errors
            occur during delivery.
        """
        ...


class SMTPEmailProvider:
    """Production implementation of EmailProvider that dispatches email  asynchronously
    via SMTP.

    Uses the `aiosmtplib` library to establish a secure connection using TLS, builds
    MIME-encoded HTML emails, and handles SMTP server connection lifecycle.
    """

    async def send(
        self,
        *,
        to: str | list[str],
        subject: str,
        html_content: str,
        reply_to: str | None = None,
    ) -> None:
        """Asynchronously dispatches an email message using configured SMTP credentials.

        Initializes an `EmailMessage`, configures standard headers
        (From, To, Subject, Reply-To), injects HTML content,
        and establishes an SMTP transaction with TLS encryption enabled.

        Raises:
            EmailDeliveryError: If connection, authentication,
            or SMTP dispatch errors occur.
        """
        message = EmailMessage()
        message["From"] = settings.SMTP_FROM_EMAIL
        message["To"] = to if isinstance(to, str) else ", ".join(to)
        message["Subject"] = subject
        if reply_to:
            message["Reply-To"] = reply_to
        message.set_content(html_content, subtype="html")

        try:
            await aiosmtplib.send(
                message,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                start_tls=True,
            )
            logger.info("Email successfully delivered to %s", to)
        except Exception as exc:
            logger.exception("Email delivery failed for %s", to)
            raise EmailDeliveryError(f"Email delivery failed for {to}") from exc


email_provider: EmailProvider = SMTPEmailProvider()


def _build_verification_html(token: str) -> str:
    """Generates the HTML markup for the email verification template.

    Injects a unique frontend verification action URL containing the verification token
    and includes the expiration TTL configured in the application settings.
    """
    action_url = f"{settings.FRONTEND_URL}/verify?token={token}"
    return email_templates.render(
        "verification",
        action_url=action_url,
        expires_minutes=str(settings.VERIFICATION_TOKEN_TTL_MINUTES),
    )


def _build_account_lock_html() -> str:
    """Generates the HTML content for the account lockout warning email template.

    Computes and injects the account lockout duration in minutes from the application
    settings.
    """
    minutes = settings.LOCKOUT_WINDOW // 60
    return email_templates.render(
        "account_lock",
        minutes=str(minutes),
    )


def _build_password_reset_html(token: str) -> str:
    """Generates the HTML markup for the password reset email template.

    Constructs a reset action link containing the reset token a nd specifies the reset
    window expiration TTL configured in the application settings.
    """
    action_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    return email_templates.render(
        "password_reset",
        action_url=action_url,
        expires_minutes=str(settings.PASSWORD_RESET_TOKEN_TTL_MINUTES),
    )


def _build_onboarding_html() -> str:
    """Generates the HTML markup for the new user onboarding welcome email template.

    Injects the direct application dashboard path as the action URL.
    """
    action_url = f"{settings.FRONTEND_URL}/dashboard"
    return email_templates.render(
        "onboarding",
        action_url=action_url,
    )


def _build_notification_html(
    *,
    reference_id: str,
    first_name: str,
    last_name: str | None,
    email: str,
    subject: str,
    message: str,
) -> str:
    """Constructs the HTML markup for support staff notification emails.

    HTML-escapes user-supplied text parameters (name, email, subject, message) to
    prevent HTML/script injection attacks within the support email client.
    """
    escaped_full_name = html.escape(
        f"{first_name} {last_name}".strip() if last_name else first_name
    )
    escaped_email = html.escape(email)
    escaped_subject = html.escape(subject)
    escaped_message = html.escape(message)
    return email_templates.render(
        "notification",
        reference_id=reference_id,
        escaped_full_name=escaped_full_name,
        escaped_email=escaped_email,
        escaped_subject=escaped_subject,
        escaped_message=escaped_message,
    )


def _build_confirmation_html(
    *,
    first_name: str,
    reference_id: str,
) -> str:
    """Constructs the HTML markup confirming receipt of contact forms to users.

    HTML-escapes the user's first name to prevent injection vulnerability and references
    the unique ticket identifier for customer tracking.
    """
    safe_name = html.escape(first_name)
    return email_templates.render(
        "confirmation",
        safe_name=safe_name,
        reference_id=reference_id,
    )


def _build_security_alert_html(detected_at: datetime) -> str:
    """Generates the HTML markup alerting users of a security incident (e.g. refresh
    token reuse).

    Formats the UTC timestamp representing when the security anomaly was detected.
    """
    formatted_time = detected_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    return email_templates.render(
        "security_alert",
        formatted_time=formatted_time,
    )


async def send_verification_email(to: str, token: str) -> None:
    """Dispatches a verification email to a new user.

    Generates the template markup with the active token, and sends it
    via the configured provider.

    Raises:
        EmailDeliveryError: If email dispatch fails.
    """
    html_content = _build_verification_html(token)
    await email_provider.send(
        to=to,
        subject=settings.VERIFICATION_SUBJECT,
        html_content=html_content,
    )


async def send_account_lock_email(to: str) -> None:
    """Dispatches a lockout notification warning email to a user.

    Generates the lock warning template and sends it via the configured provider.

    Raises:
        EmailDeliveryError: If email dispatch fails.
    """
    html_content = _build_account_lock_html()
    await email_provider.send(
        to=to,
        subject=settings.ACCOUNT_LOCK_SUBJECT,
        html_content=html_content,
    )


async def send_password_reset_email(to: str, token: str) -> None:
    """Dispatches a password reset link email to a user.

    Generates the template markup containing the reset token and sends it
    via the configured provider.

    Raises:
        EmailDeliveryError: If email dispatch fails.
    """
    html_content = _build_password_reset_html(token)
    await email_provider.send(
        to=to,
        subject=settings.PASSWORD_RESET_SUBJECT,
        html_content=html_content,
    )


async def send_onboarding_email(to: str) -> None:
    """Dispatches a welcome onboarding email to a new user.

    Generates the onboarding welcome template and sends it
    via the configured provider.

    Raises:
        EmailDeliveryError: If email dispatch fails.
    """
    html_content = _build_onboarding_html()
    await email_provider.send(
        to=to,
        subject=settings.ONBOARDING_SUBJECT,
        html_content=html_content,
    )


async def send_security_alert_email(to: str, detected_at: datetime) -> None:
    """Dispatches a security alert warning email to a user.

    Generates the security template containing incident time and sends it
    via the configured provider.

    Raises:
        EmailDeliveryError: If email dispatch fails.
    """
    html_content = _build_security_alert_html(detected_at)
    await email_provider.send(
        to=to,
        subject=settings.SECURITY_ALERT_SUBJECT,
        html_content=html_content,
    )


async def send_contact_notification(
    *,
    reference_id: str,
    first_name: str,
    last_name: str | None,
    email: str,
    subject: str,
    message: str,
) -> None:
    """Dispatches a notification email containing contact ticket info to the support
    team inbox.

    Injects support routing parameters, references the customer's email
    in the Reply-To header, and sends the HTML email via the configured provider.

    Raises:
        EmailDeliveryError: If email dispatch fails.
    """
    html_content = _build_notification_html(
        reference_id=reference_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        subject=subject,
        message=message,
    )
    await email_provider.send(
        to=settings.CONTACT_RECIPIENT_EMAIL,
        subject=settings.CONTACT_NOTIFICATION_SUBJECT,
        html_content=html_content,
        reply_to=email,
    )


async def send_contact_confirmation(
    *,
    to_email: str,
    first_name: str,
    reference_id: str,
) -> None:
    """Dispatches a contact form receipt confirmation email to the user.

    Attempts to send the email confirmation and catches/logs any errors to prevent
    blocking the main contact form submission workflow.
    """
    html_content = _build_confirmation_html(
        first_name=first_name,
        reference_id=reference_id,
    )
    try:
        await email_provider.send(
            to=to_email,
            subject=settings.CONTACT_CONFIRMATION_SUBJECT,
            html_content=html_content,
        )
    except Exception:
        logger.exception(
            "Unexpected error sending contact confirmation to %s (ref %s)",
            to_email,
            reference_id,
        )


async def send_newsletter_welcome_email(*, to: str, unsubscribe_token: str) -> None:
    """Dispatches a welcome email to a new newsletter subscriber.

    Injects a dynamic unsubscribe token, renders the newsletter template,
    and sends the email.

    Raises:
        EmailDeliveryError: If email dispatch fails.
    """
    html_content = email_templates.render(
        "newsletter_welcome",
        unsubscribe_token=unsubscribe_token,
    )
    await email_provider.send(
        to=to,
        subject=settings.NEWSLETTER_WELCOME_SUBJECT,
        html_content=html_content,
    )
