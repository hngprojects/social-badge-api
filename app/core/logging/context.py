import contextvars
import uuid
from typing import Any

# Module-level ContextVar — one per async task, safe under concurrent requests.
request_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "request_context", default=None
)


class RequestContextLogger:
    """Async context manager that binds request-scoped data to the log context.

    All log calls made within the `async with` block automatically include
    the request_id and any additional key-value pairs passed at construction.

    Usage::
        async with RequestContextLogger(request_id="abc123", method="GET"):
            logger.info("handled")   # → includes request_id, method
    """

    def __init__(self, request_id: str | None = None, **context: Any) -> None:
        self.request_id = request_id or str(uuid.uuid4())[:8]
        self.context: dict[str, Any] = {"request_id": self.request_id, **context}
        self._token: contextvars.Token[dict[str, Any] | None] | None = None

    async def __aenter__(self) -> RequestContextLogger:
        self._token = request_context.set(self.context)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._token is not None:
            request_context.reset(self._token)
            self._token = None
