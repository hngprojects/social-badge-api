import logging
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.newsletter import NewsletterSubscriber
from app.services.email import send_newsletter_welcome_email

logger = logging.getLogger(__name__)


def _make_unsubscribe_token() -> str:
    """
    Generates a secure, cryptographically random hexadecimal unsubscribe token.

    Generates a 64-character hex string to prevent token guessing attacks.
    """
    return secrets.token_hex(32)


async def subscribe(
    session: AsyncSession,
    email: str,
) -> tuple[NewsletterSubscriber, bool]:
    """
    Subscribes or reactivates an email subscription to the newsletter.

    Checks if a subscription already exists for the email.
    If the subscription is active, returns it. If inactive or new,
    creates/reactivates the record with a fresh unsubscribe token,
    commits the database session, and sends a welcome newsletter email.
    Handles potential concurrent subscription race conditions
    by catching `IntegrityError` and rolling back.
    """
    result = await session.execute(
        select(NewsletterSubscriber).where(NewsletterSubscriber.email == email)
    )
    subscriber = result.scalar_one_or_none()

    if subscriber is not None and subscriber.is_active:
        return subscriber, False

    if subscriber is None:
        subscriber = NewsletterSubscriber(
            email=email,
            unsubscribe_token=_make_unsubscribe_token(),
        )
        session.add(subscriber)
    else:
        subscriber.is_active = True
        subscriber.unsubscribe_token = _make_unsubscribe_token()
        subscriber.unsubscribed_at = None

    try:
        await session.commit()
        await session.refresh(subscriber)
    except IntegrityError:
        await session.rollback()
        result = await session.execute(
            select(NewsletterSubscriber).where(NewsletterSubscriber.email == email)
        )
        subscriber = result.scalar_one_or_none()
        if subscriber is None:  # pragma: no cover
            raise RuntimeError(
                f"Subscriber row missing after IntegrityError for {email!r}"
            ) from None
        return subscriber, False

    try:
        await send_newsletter_welcome_email(
            to=email,
            unsubscribe_token=subscriber.unsubscribe_token,
        )
    except Exception:
        logger.exception("Failed to send newsletter welcome email to %s", email)

    return subscriber, True


async def unsubscribe(session: AsyncSession, token: str) -> bool:
    """
    Unsubscribes a subscriber from the newsletter using their unique unsubscribe token.

    Queries the database by token, sets `is_active` to False,
    records the current UTC unsubscription timestamp, and commits.
    Returns True if a matching subscriber was found, otherwise False.
    """
    result = await session.execute(
        select(NewsletterSubscriber).where(
            NewsletterSubscriber.unsubscribe_token == token
        )
    )
    subscriber = result.scalar_one_or_none()

    if subscriber is None:
        return False

    if subscriber.is_active:
        subscriber.is_active = False
        subscriber.unsubscribed_at = datetime.now(UTC)
        await session.commit()

    return True
