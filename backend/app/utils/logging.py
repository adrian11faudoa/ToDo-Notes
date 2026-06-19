"""
utils/logging.py
────────────────
Structured logging configuration.
In production (AWS): outputs JSON to stdout → CloudWatch Logs Insights.
In development: outputs colourised human-readable logs.
"""

from __future__ import annotations
import logging
import sys
from typing import Any

import structlog
from app.core.config import get_settings

settings = get_settings()


def configure_logging() -> None:
    """
    Call once at application startup (in lifespan).
    Sets up structlog with appropriate renderer for environment.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.is_production:
        # JSON output for CloudWatch Logs Insights queries
        renderer = structlog.processors.JSONRenderer()
    else:
        # Human-readable colourised output for local dev
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # Quiet noisy third-party loggers
    for name in ("uvicorn.access", "sqlalchemy.engine", "boto3", "botocore", "s3transfer"):
        logging.getLogger(name).setLevel(logging.WARNING)

    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("alembic").setLevel(logging.INFO)
