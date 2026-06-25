import os
import sys

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings


def is_testing_environment() -> bool:
    """Checks whether the application is running inside a test environment.

    Verifies the presence of pytest in sys.modules or environment variables to decide on
    using an in-memory rate limiting database instead of Redis.
    """
    return (
        "pytest" in sys.modules
        or os.getenv("PYTEST_CURRENT_TEST") is not None
        or os.getenv("TESTING") == "True"
    )


_redis_uri = "memory://" if is_testing_environment() else str(settings.REDIS_URL)

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_redis_uri,
)
