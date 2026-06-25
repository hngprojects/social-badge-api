import secrets
import string

SLUG_LENGTH = 12
SLUG_ALPHABET = string.ascii_letters + string.digits


def generate_share_slug(length: int = SLUG_LENGTH) -> str:
    """
    Generates a cryptographically secure random slug.

    Uses character choices from the combined alphanumeric alphabet (letters and digits)
    to guarantee URL-safe slugs for resource sharing.
    """
    return "".join(secrets.choice(SLUG_ALPHABET) for _ in range(length))
