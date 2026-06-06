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
    """Return all available contact form subject options."""
    return _CACHED_SUBJECTS


def _generate_reference_id() -> str:
    year = datetime.now(UTC).year
    suffix = "".join(secrets.choice(_REFERENCE_ALPHABET) for _ in range(6))
    return f"CONTACT-{year}-{suffix}"


async def submit_contact_form(payload: ContactRequest) -> str:
    reference_id = _generate_reference_id()
    subject_label = _TOPIC_LABELS.get(payload.subject, payload.subject.value)

    logger.info(
        "Contact form submitted: ref=%s topic=%s",
        reference_id,
        payload.subject,
    )

    # Notify the team — let errors propagate so the endpoint can return 502
    await send_contact_notification(
        reference_id=reference_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=str(payload.email),
        subject=subject_label,
        message=payload.message,
    )

    # Best-effort confirmation email to the sender — never fails the request
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
