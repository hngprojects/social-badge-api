import time
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from app.core import sanitizer
from app.core.logging import RequestContextLogger


def _client_ip(request: Request) -> str:
    """Helper to extract client IP address from request headers or connection metadata.

    Supports X-Forwarded-For, X-Real-IP, and ASGI request client host properties.
    """
    if forwarded := request.headers.get("X-Forwarded-For"):
        return forwarded.split(",")[0].strip()
    if real_ip := request.headers.get("X-Real-IP"):
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """FastAPI/Starlette middleware to capture, format, and log API request and response
    details.

    Generates a unique request-id per request to associate related logs in multi-tenant
    contexts.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Intercepts the incoming HTTP request, logs start details, executes down-chain
        handlers, and logs completion metrics.

        Uses RequestContextLogger context manager to tie the unique request ID to all
        logs generated during request resolution. Sanitizes query parameters and headers
        to avoid leakage.
        """
        request_id = uuid.uuid4().hex
        client_ip = _client_ip(request)
        method = request.method
        path = request.url.path
        query = sanitizer.sanitize_query(request.url.query)
        user_agent = (request.headers.get("user-agent", "") or "")[:200]
        safe_hdrs = sanitizer.sanitize_headers(dict(request.headers))

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
            is_health_check = path in {"/", "/health", "/api/v1/health"}

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
