"""
Structured Logging Configuration.

Provides JSON-structured logging via loguru with:
- Console output (human-readable in dev, JSON in prod)
- File rotation with retention
- Correlation IDs per request
- Sensitive field redaction

Usage:
    from config.logging_config import setup_logging, get_logger
    setup_logging()
    logger = get_logger(__name__)
    logger.info("Trade executed", symbol="RELIANCE", qty=10, price=2500.0)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from loguru import logger


# Fields that must never appear in logs
_SENSITIVE_FIELDS = {"api_key", "api_secret", "password", "token", "secret"}


def _redact_sensitive(record: dict[str, Any]) -> bool:
    """
    Loguru sink filter that redacts sensitive keys from the log record's extra dict.

    Args:
        record: The loguru log record.

    Returns:
        True (always allow the record through; redaction happens in-place).
    """
    extra: dict[str, Any] = record.get("extra", {})
    for key in list(extra.keys()):
        if key.lower() in _SENSITIVE_FIELDS:
            extra[key] = "***REDACTED***"
    return True


def _json_serializer(record: dict[str, Any]) -> str:
    """
    Custom JSON log formatter compatible with loguru.

    Args:
        record: The loguru log record.

    Returns:
        JSON-formatted log string.
    """
    import json

    log_entry = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "logger": record["name"],
        "function": record["function"],
        "line": record["line"],
        "message": record["message"],
        **record["extra"],
    }
    if record["exception"]:
        log_entry["exception"] = record["exception"]
    return json.dumps(log_entry, default=str)


def setup_logging(
    level: str = "INFO",
    log_format: str = "console",
    log_file: str = "logs/app.log",
    rotation: str = "10 MB",
    retention: str = "7 days",
) -> None:
    """
    Configure application-wide structured logging.

    Args:
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_format: Output format - 'console' (pretty) or 'json' (structured).
        log_file: Path to the rotating log file.
        rotation: Loguru rotation trigger (e.g. '10 MB', '1 day').
        retention: How long to keep rotated files.
    """
    # Remove default loguru handler
    logger.remove()

    # --- Console sink ---
    if log_format == "json":
        logger.add(
            sys.stdout,
            level=level,
            format="{message}",
            serialize=True,
            filter=_redact_sensitive,
            colorize=False,
        )
    else:
        logger.add(
            sys.stdout,
            level=level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            ),
            filter=_redact_sensitive,
            colorize=True,
        )

    # --- File sink (always JSON for machine-parseable audit trail) ---
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(log_path),
        level=level,
        format="{message}",
        serialize=True,
        rotation=rotation,
        retention=retention,
        filter=_redact_sensitive,
        enqueue=True,       # Thread-safe async logging
        backtrace=True,
        diagnose=False,     # Disable in production to avoid leaking locals
    )

    # --- Intercept stdlib logging (for third-party libraries) ---
    _intercept_stdlib_logging(level)

    logger.info(
        "Logging configured",
        level=level,
        format=log_format,
        log_file=str(log_path),
    )


class _InterceptHandler(logging.Handler):
    """
    Redirect standard library logging records to loguru.

    Allows libraries that use `logging.getLogger(...)` to be captured
    by loguru's structured pipeline.
    """

    def emit(self, record: logging.LogRecord) -> None:
        # Find the caller's depth to get the right line number
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno  # type: ignore[assignment]

        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def _intercept_stdlib_logging(level: str) -> None:
    """
    Replace all stdlib logging handlers with the loguru intercept handler.

    Args:
        level: Minimum log level string.
    """
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for name in logging.root.manager.loggerDict:
        log = logging.getLogger(name)
        log.handlers = [_InterceptHandler()]
        log.propagate = False


def get_logger(name: str) -> "logger":  # type: ignore[valid-type]
    """
    Return a loguru logger bound to the given module name.

    Args:
        name: Module name (use __name__).

    Returns:
        Loguru logger instance.
    """
    return logger.bind(module=name)