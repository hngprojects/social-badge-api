import logging
import secrets
import string
from datetime import UTC, datetime

from app.schemas.contact import ContactRequest, ContactSubjectOption, ContactTopic
from app.services.email import (
    send_contact_confirmation,
    send_contact_notification,
)

logger = logging.getLogger(__name__)

_TOPIC_LABELS: dict[ContactTopic, str] = {
    ContactTopic.GENERAL: "General Question",
    ContactTopic.PARTNERSHIP: "Partnership Idea",
    ContactTopic.BUG_REPORT: "Bug Report",
    ContactTopic.FEEDBACK: "Feedback",
    ContactTopic.BILLING: "Billing",
    ContactTopic.OTHER: "Other",
}

_REFERENCE_ALPHABET = string.ascii_uppercase + string.digits

_CACHED_SUBJECTS: list[ContactSubjectOption] = [
    ContactSubjectOption(value=topic.value, label=label)
    for topic, label in _TOPIC_LABELS.items()
]


def get_contact_subjects() -> list[ContactSubjectOption]:
    """
    Retrieves all static contact subject options and their human-readable labels.

    Returns a cached list of ContactSubjectOption objects
    to avoid recreating lists dynamically.
    """
    return _CACHED_SUBJECTS


def _generate_reference_id() -> str:
    """
    Generates a cryptographically secure, unique tracking reference ID
    for contact submissions.

    Constructs a reference string in the format
    `CONTACT-<CURRENT_YEAR>-<RANDOM_ALPHANUMERIC_SUFFIX>`.
    """
    year = datetime.now(UTC).year
    suffix = "".join(secrets.choice(_REFERENCE_ALPHABET) for _ in range(6))
    return f"CONTACT-{year}-{suffix}"


async def submit_contact_form(payload: ContactRequest) -> str:
    """
    Processes contact form requests, generates reference IDs, and sends emails.

    Generates a unique tracking reference,
    sends a detailed notification email to the support inbox,
    and triggers a confirmation receipt to the user's email.
    Errors during receipt delivery are swallowed on a best-effort basis,
    and the reference ID is returned.
    """
    reference_id = _generate_reference_id()
    subject_label = _TOPIC_LABELS.get(payload.subject, payload.subject.value)

    logger.info(
        "Contact form submitted: ref=%s topic=%s",
        reference_id,
        payload.subject,
    )

    await send_contact_notification(
        reference_id=reference_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=str(payload.email),
        subject=subject_label,
        message=payload.message,
    )

    try:
        await send_contact_confirmation(
            to_email=str(payload.email),
            first_name=payload.first_name,
            reference_id=reference_id,
        )
    except Exception:
        logger.exception(
            "Unexpected error sending contact confirmation for ref=%s",
            reference_id,
        )

    return reference_id
