import logging
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.logging.context import request_context
from app.core.logging.format import LogFormat
from app.core.sanitizer import data_sanitizer


class InterceptHandler(logging.Handler):
    """Redirect all standard-library log records into Loguru.

    This makes third-party libraries (SQLAlchemy, httpx, uvicorn, etc.) whose
    logs arrive via ``logging.getLogger(name)`` visible in the Loguru pipeline
    with the correct caller location and request context attached.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Walk up the call stack until we leave the standard logging module
        # so Loguru reports the original call site, not logging internals.
        frame = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1

        ctx = request_context.get() or {}
        (
            logger.opt(depth=depth, exception=record.exc_info)
            .bind(**ctx)
            .log(level, record.getMessage())
        )


def _context_patcher(record: Any) -> None:  # type: ignore[type-arg]
    """Merge the current request context into every Loguru record's extra dict."""
    ctx = request_context.get()
    if ctx:
        record["extra"].update(ctx)

    # Globally sanitize PII from all interpolated log messages
    record["message"] = data_sanitizer.sanitize_for_logging(record["message"])


def setup_logging(
    log_level: str = "INFO",
    log_file: Path = Path("logs/app.log"),
    environment: str = "local",
) -> None:
    """Configure Loguru as the sole logging backend for the application.

    Safe to call multiple times — Loguru's ``logger.remove()`` ensures sinks
    are not duplicated across reloads (e.g., during ``uvicorn --reload``).
    """
    is_local = environment.lower() in {"local", "dev", "development"}

    # Remove all pre-existing Loguru handlers (handles reload safety)
    logger.remove()

    # Redirect the stdlib root logger through our InterceptHandler
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    logging.root.setLevel(log_level)

    # Prevent third-party loggers from adding their own handlers while still
    # allowing records to propagate up to the root (and hence InterceptHandler).
    for name in list(logging.root.manager.loggerDict):
        lib_logger = logging.getLogger(name)
        lib_logger.handlers = []
        lib_logger.propagate = True

    logging.getLogger("uvicorn.access").propagate = False

    log_file.parent.mkdir(parents=True, exist_ok=True)
    error_log_file = log_file.with_name(log_file.stem + "_errors" + log_file.suffix)

    # Sink 1: stdout (coloured in local, JSON in production)
    logger.add(
        sys.stdout,
        level=log_level,
        colorize=is_local,
        serialize=not is_local,  # JSON lines in staging/production
        backtrace=False,
        diagnose=is_local,  # full variable introspection locally only
        format=lambda rec: LogFormat(rec).console(),
    )

    # Sink 2: rotating info+ file (always JSON for structured ingestion)
    logger.add(
        str(log_file),
        level="INFO",
        rotation="10 MB",
        retention="10 days",
        compression="zip",
        enqueue=True,  # thread/async-safe writes
        backtrace=True,
        diagnose=False,  # never dump locals to disk (secrets)
        serialize=True,
        format=lambda rec: LogFormat(rec).file(),
    )

    # Sink 3: error-only file (long retention for post-mortems)
    logger.add(
        str(error_log_file),
        level="ERROR",
        rotation="10 MB",
        retention="60 days",
        compression="zip",
        enqueue=True,
        backtrace=True,
        diagnose=False,
        serialize=True,
        format=lambda rec: LogFormat(rec).file(),
    )

    # Attach the context patcher to every record
    logger.configure(patcher=_context_patcher)

    logger.info(
        "Logging configured | level={} env={} file={}",
        log_level,
        environment,
        log_file,
    )
