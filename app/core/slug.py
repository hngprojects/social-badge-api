import secrets
import string

# Default length for generated slugs to balance readability and collision avoidance.
SLUG_LENGTH = 12
SLUG_ALPHABET = string.ascii_letters + string.digits


def generate_share_slug(length: int = SLUG_LENGTH) -> str:
    return "".join(secrets.choice(SLUG_ALPHABET) for _ in range(length))
