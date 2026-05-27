import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request

import app.core.pillow as _pillow_init  # noqa: F401 — must precede any Image.open() call
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.middleware import ContentSizeLimitMiddleware
from app.core.rate_limit import limiter
from app.db.redis import redis_pool
from app.routers.v1 import api_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    yield
    await redis_pool.disconnect()


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)


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

app.add_middleware(
    ContentSizeLimitMiddleware,
    max_body_bytes=settings.MAX_CONTENT_BODY_SIZE,
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

register_exception_handlers(app)


@app.get("/")
@limiter.limit("15/minute")
def root(request: Request) -> dict[str, str]:
    return {"message": f"{settings.PROJECT_NAME} is running"}
