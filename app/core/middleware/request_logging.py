import time
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import RequestContextLogger
from app.core.sanitizer import data_sanitizer


def _client_ip(request: Request) -> str:
    if forwarded := request.headers.get("X-Forwarded-For"):
        return forwarded.split(",")[0].strip()
    if real_ip := request.headers.get("X-Real-IP"):
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with a unique request ID and response metrics.

    Attaches ``request_id``, ``method``, ``path``, ``client_ip``, and
    ``user_agent`` to the Loguru context for the duration of the request so
    all downstream log calls carry those fields automatically.

    Response status and elapsed time are logged at request completion.
    Unhandled exceptions are re-raised after logging so FastAPI's exception
    handlers remain in control of the response.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = uuid.uuid4().hex
        client_ip = _client_ip(request)
        method = request.method
        path = request.url.path
        query = data_sanitizer.sanitize_query(request.url.query)
        user_agent = (request.headers.get("user-agent", "") or "")[:200]
        safe_hdrs = data_sanitizer.sanitize_headers(dict(request.headers))

        ctx: dict = {
            "client_ip": client_ip,
            "method": method,
            "path": path,
            "user_agent": user_agent,
        }
        if query:
            ctx["query"] = query
        if safe_hdrs:
            ctx["headers"] = safe_hdrs

        async with RequestContextLogger(request_id=request_id, **ctx):
            is_health_check = path in {"/", "/health", "/api/v1/health", "/metrics"}

            if not is_health_check:
                logger.info("→ {} {}", method, path)

            start = time.perf_counter()

            try:
                response: Response = await call_next(request)
            except Exception:
                logger.error(
                    "✗ {} {} — unhandled exception after {:.1f}ms",
                    method,
                    path,
                    (time.perf_counter() - start) * 1000,
                )
                raise

            elapsed = (time.perf_counter() - start) * 1000
            level = "WARNING" if response.status_code >= 400 else "INFO"

            if not is_health_check or response.status_code >= 400:
                logger.log(
                    level,
                    "← {} {} {} {:.1f}ms",
                    method,
                    path,
                    response.status_code,
                    elapsed,
                )

            return response
