import logging
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from app.core import sanitizer
from app.core.logging.context import request_context
from app.core.logging.format import LogFormat


class InterceptHandler(logging.Handler):
    """
    Redirect all standard-library log records into Loguru.

    This makes third-party libraries (SQLAlchemy, httpx, uvicorn, etc.) whose
    logs arrive via ``logging.getLogger(name)`` visible in the Loguru pipeline
    with the correct caller location and request context attached.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """
        Translates a standard library logging record into a Loguru record.

        Resolves caller frame depth dynamically and binds active
        asynchronous request context.
        """
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        ctx = request_context.get() or {}
        (
            logger.opt(depth=depth, exception=record.exc_info)
            .bind(**ctx)
            .log(level, record.getMessage())
        )


def _context_patcher(record: Any) -> None:
    """
    Loguru record patcher that injects active async request context and
    sanitizes log messages.

    Invoked before log records are serialized or outputted to console/file sinks,
    ensuring sensitive data is masked.
    """
    ctx = request_context.get()
    if ctx:
        record["extra"].update(ctx)

    record["message"] = sanitizer.sanitize_for_logging(record["message"])


def setup_logging(
    log_level: str = "INFO",
    log_file: Path = Path("logs/app.log"),
    environment: str = "local",
) -> None:
    """
    Configures the Loguru logger system as the central backend for
    application-wide logging.

    Registers standard library log interception, defines console and rotating file
    logging sinks, and binds context-aware message patching.
    """
    is_local = environment.lower() in {"local", "dev", "development"}

    logger.remove()

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    logging.root.setLevel(log_level)

    for name in list(logging.root.manager.loggerDict):
        lib_logger = logging.getLogger(name)
        lib_logger.handlers = []
        lib_logger.propagate = True

    logging.getLogger("uvicorn.access").propagate = False

    log_file.parent.mkdir(parents=True, exist_ok=True)
    error_log_file = log_file.with_name(log_file.stem + "_errors" + log_file.suffix)

    logger.add(
        sys.stdout,
        level=log_level,
        colorize=is_local,
        serialize=not is_local,
        backtrace=False,
        diagnose=is_local,
        format=lambda rec: LogFormat(rec).console(),
    )

    logger.add(
        str(log_file),
        level="INFO",
        rotation="10 MB",
        retention="10 days",
        compression="zip",
        enqueue=True,
        backtrace=True,
        diagnose=False,
        serialize=True,
        format=lambda rec: LogFormat(rec).file(),
    )

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

    logger.configure(patcher=_context_patcher)

    logger.info(
        "Logging configured | level={} env={} file={}",
        log_level,
        environment,
        log_file,
    )
