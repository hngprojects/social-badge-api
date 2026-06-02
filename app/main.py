from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request

import app.core.pillow as _pillow_init  # noqa: F401 — must precede any Image.open() call
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.metrics import metrics_response
from app.core.middleware import (
    ContentSizeLimitMiddleware,
    PrometheusMetricsMiddleware,
    RequestLoggingMiddleware,
)
from app.core.rate_limit import limiter
from app.db.redis import redis_pool
from app.routers.v1 import api_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    setup_logging(
        log_level=settings.LOG_LEVEL,
        log_file=settings.LOG_FILE,
        environment=settings.ENVIRONMENT,
    )

    yield
    await redis_pool.disconnect()


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.add_middleware(PrometheusMetricsMiddleware)
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
    return {"message": f"{settings.PROJECT_NAME} is running"}


def _verify_metrics_token(authorization: Annotated[str | None, Header()] = None) -> None:
    token = settings.METRICS_TOKEN
    if not token:
        return
    if authorization != f"Bearer {token}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@app.get("/metrics", include_in_schema=False)
def metrics(_: Annotated[None, Depends(_verify_metrics_token)]) -> Response:
    return metrics_response()
