from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import ContentSizeLimitMiddleware, RequestLoggingMiddleware
from app.core.rate_limit import limiter
from app.db.redis import redis_pool
from app.routers.v1 import api_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    Manages application startup and shutdown lifecycle events.

    Initializes structured application logging on startup and cleanly terminates
    the Redis connection pool on shutdown to prevent socket leaks.
    Executed by the ASGI server worker process with minimal overhead,
    as establishing logging and closing Redis connections are one-off operations
    occurring outside request-response loops. This lifecycle context is public,
    requires no authentication, and is not rate-limited.
    """
    setup_logging(
        log_level=settings.LOG_LEVEL,
        log_file=settings.LOG_FILE,
        environment=settings.ENVIRONMENT,
    )

    yield
    await redis_pool.disconnect()


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    ContentSizeLimitMiddleware,
    max_body_bytes=settings.MAX_CONTENT_BODY_SIZE,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "Accept",
        "Accept-Language",
        "Origin",
    ],
    expose_headers=["Content-Length"],
)


app.include_router(api_router, prefix=settings.API_V1_PREFIX)

register_exception_handlers(app)


@app.get("/")
@limiter.limit("15/minute")
def root(request: Request) -> dict[str, str]:
    """
    Serves a basic system health-check response confirming that the service is running.

    This public endpoint requires no authentication and returns a simple JSON payload
    containing the project name. The handler is extremely lightweight,
    returning static information without querying the database or Redis
    (excluding rate limiter checks).
    It is rate-limited to 15 requests per minute per client IP.
    """
    return {"message": f"{settings.PROJECT_NAME} is running"}
