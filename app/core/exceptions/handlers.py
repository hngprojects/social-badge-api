import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.response import ErrorResponse

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(
        request: Request, exc: RateLimitExceeded
    ) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content=ErrorResponse(message="Rate limit exceeded").model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(message=str(exc.detail)).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        if not errors:
            return JSONResponse(
                status_code=422,
                content=ErrorResponse(message="Validation Error").model_dump(),
            )
        err = errors[0]
        loc_parts = [str(item) for item in err["loc"] if item != "body"]
        loc = " ".join(part.replace("_", " ").title() for part in loc_parts)
        msg = err["msg"]
        if msg.startswith("Value error, "):
            msg = msg.replace("Value error, ", "")
        elif ":" in msg:
            msg = msg.split(":")[-1].strip()
        if msg:
            msg = msg[0].lower() + msg[1:]
        full_message = f"{loc}: {msg}" if loc else msg.capitalize()
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(message=full_message).model_dump(),
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled exception occurred")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(message="Internal Server Error").model_dump(),
        )
