import asyncio
import html
import logging
from email.message import EmailMessage

import aiosmtplib
import resend
import resend.exceptions

from app.core.config import settings
from app.core.exceptions import EmailDeliveryError

logger = logging.getLogger(__name__)

resend.api_key = settings.RESEND_API_KEY


def _build_verification_html(token: str) -> str:
    return (
        "<h2>Welcome to Flare Tag</h2>"
        "<p>Please verify your email address by clicking the link below:</p>"
        f'<p><a href="{settings.FRONTEND_URL}/verify?token={token}">'
        "Verify Email</a></p>"
        "<p>This link expires in 30 minutes.</p>"
    )


def _build_account_lock_html() -> str:
    minutes = settings.LOCKOUT_WINDOW // 60
    return (
        "<h2>Your Flare Tag account has been temporarily locked</h2>"
        "<p>We detected too many failed login attempts on your account.</p>"
        f"<p>Your account has been locked for {minutes} minutes. "
        "Please try again after that time.</p>"
        "<p>If this wasn't you, we recommend changing your password "
        "once you regain access.</p>"
    )


def _build_password_reset_html(token: str) -> str:
    return (
        "<h2>Password Reset Request</h2>"
        "<p>We received a request to reset your Flare Tag password. "
        "Click the link below to set a new password:</p>"
        f'<p><a href="{settings.FRONTEND_URL}/reset-password?token={token}">'
        "Reset Password</a></p>"
        "<p>This link expires in 30 minutes. If you didn't request a password "
        "reset, you can safely ignore this email.</p>"
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
    full_name = f"{first_name} {last_name}".strip() if last_name else first_name
    full_name = html.escape(full_name)
    email = html.escape(email)
    escaped_message = html.escape(message)
    return (
        f"<h2>New Contact Form Submission</h2>"
        f"<p><strong>Reference ID:</strong> {reference_id}</p>"
        f"<p><strong>Name:</strong> {full_name}</p>"
        f"<p><strong>Email:</strong> <a href='mailto:{email}'>{email}</a></p>"
        f"<p><strong>Topic:</strong> {subject}</p>"
        f"<hr />"
        f"<p><strong>Message:</strong></p>"
        f"<p>{escaped_message}</p>"
    )


def _build_confirmation_html(
    *,
    first_name: str,
    reference_id: str,
) -> str:
    """HTML confirmation email sent to the person who submitted the contact form."""
    safe_name = html.escape(first_name)
    return (
        f"<h2>Thanks for reaching out, {safe_name}!</h2>"
        f"<p>We've received your message and will get back to you "
        f"within one business day.</p>"
        f"<p><strong>Your reference ID:</strong> {reference_id}</p>"
        f"<p>If you need to follow up, just reply to this email and "
        f"include your reference ID.</p>"
        f"<p>— The Flare Tag Team</p>"
    )


async def _send_smtp_email(
    *,
    to: str | list[str],
    subject: str,
    html_content: str,
    reply_to: str | None = None,
) -> None:
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
        logger.info("Email successfully delivered via SMTP fallback to %s", to)
    except Exception as exc:
        logger.exception("SMTP fallback failed for %s", to)
        raise EmailDeliveryError(f"SMTP fallback failed for {to}") from exc


async def send_verification_email(to: str, token: str) -> None:
    params: resend.Emails.SendParams = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to],
        "subject": settings.VERIFICATION_SUBJECT,
        "html": _build_verification_html(token),
    }

    try:
        await asyncio.to_thread(resend.Emails.send, params)
    except resend.exceptions.ResendError:
        logger.warning(
            "Resend failed for verification email to %s, trying SMTP fallback", to
        )
        await _send_smtp_email(
            to=to,
            subject=settings.VERIFICATION_SUBJECT,
            html_content=params["html"],
        )
    except Exception as exc:
        logger.exception("Unexpected error sending verification email to %s", to)
        raise EmailDeliveryError(f"Failed to send verification email to {to}") from exc


async def send_account_lock_email(to: str) -> None:
    params: resend.Emails.SendParams = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to],
        "subject": settings.ACCOUNT_LOCK_SUBJECT,
        "html": _build_account_lock_html(),
    }

    try:
        await asyncio.to_thread(resend.Emails.send, params)
    except resend.exceptions.ResendError:
        logger.warning(
            "Resend failed for account lock email to %s, trying SMTP fallback", to
        )
        await _send_smtp_email(
            to=to,
            subject=settings.ACCOUNT_LOCK_SUBJECT,
            html_content=params["html"],
        )
    except Exception as exc:
        logger.exception("Unexpected error sending account lock email to %s", to)
        raise EmailDeliveryError(f"Failed to send account lock email to {to}") from exc


async def send_password_reset_email(to: str, token: str) -> None:
    params: resend.Emails.SendParams = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to],
        "subject": settings.PASSWORD_RESET_SUBJECT,
        "html": _build_password_reset_html(token),
    }

    try:
        await asyncio.to_thread(resend.Emails.send, params)
    except resend.exceptions.ResendError:
        logger.warning(
            "Resend failed for password reset email to %s, trying SMTP fallback", to
        )
        await _send_smtp_email(
            to=to,
            subject=settings.PASSWORD_RESET_SUBJECT,
            html_content=params["html"],
        )
    except Exception as exc:
        logger.exception("Unexpected error sending password reset email to %s", to)
        raise EmailDeliveryError(
            f"Failed to send password reset email to {to}"
        ) from exc


async def send_contact_notification(
    *,
    reference_id: str,
    first_name: str,
    last_name: str | None,
    email: str,
    subject: str,
    message: str,
) -> None:
    params: resend.Emails.SendParams = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [settings.CONTACT_RECIPIENT_EMAIL],
        "reply_to": email,
        "subject": settings.CONTACT_NOTIFICATION_SUBJECT,
        "html": _build_notification_html(
            reference_id=reference_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            subject=subject,
            message=message,
        ),
    }
    try:
        await asyncio.to_thread(resend.Emails.send, params)
    except resend.exceptions.ResendError:
        logger.warning(
            "Resend failed for contact notification (ref %s), trying SMTP fallback",
            reference_id,
        )
        await _send_smtp_email(
            to=settings.CONTACT_RECIPIENT_EMAIL,
            subject=settings.CONTACT_NOTIFICATION_SUBJECT,
            html_content=params["html"],
            reply_to=email,
        )
    except Exception as exc:
        logger.exception(
            "Unexpected error sending contact notification for ref %s", reference_id
        )
        raise EmailDeliveryError(
            f"Failed to send contact notification for {reference_id}"
        ) from exc


async def send_contact_confirmation(
    *,
    to_email: str,
    first_name: str,
    reference_id: str,
) -> None:
    params: resend.Emails.SendParams = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to_email],
        "subject": settings.CONTACT_CONFIRMATION_SUBJECT,
        "html": _build_confirmation_html(
            first_name=first_name,
            reference_id=reference_id,
        ),
    }
    try:
        await asyncio.to_thread(resend.Emails.send, params)
    except resend.exceptions.ResendError:
        logger.warning(
            "Resend failed for contact confirmation to %s (ref %s), "
            "trying SMTP fallback",
            to_email,
            reference_id,
        )
        try:
            await _send_smtp_email(
                to=to_email,
                subject=settings.CONTACT_CONFIRMATION_SUBJECT,
                html_content=params["html"],
            )
        except Exception:
            logger.exception(
                "Final failure: SMTP fallback also failed for contact "
                "confirmation to %s (ref %s)",
                to_email,
                reference_id,
            )
    except Exception:
        logger.exception(
            "Unexpected error sending contact confirmation to %s (ref %s)",
            to_email,
            reference_id,
        )
