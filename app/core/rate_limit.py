import os
import sys

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings


def is_testing_environment() -> bool:
    return (
        "pytest" in sys.modules
        or os.getenv("PYTEST_CURRENT_TEST") is not None
        or os.getenv("TESTING") == "True"
    )


# Use in-memory storage for rate limits during tests to avoid dependency on Redis
_redis_uri = "memory://" if is_testing_environment() else str(settings.REDIS_URL)

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_redis_uri,
    # Rate-limits endpoints by client IP address
)
