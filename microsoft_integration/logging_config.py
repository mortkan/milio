"""Logging configuration for microsoft_integration service."""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path


def configure_logging(log_level: str = "INFO", log_file: str | None = None) -> None:
    """Configure structured logging for the Microsoft integration service.

    Logs go to stdout (always) and optionally to a rotating file.
    Sensitive values (tokens, secrets) must never appear in log messages —
    callers are responsible for sanitizing their own log strings.
    """
    fmt = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%S"

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates on reload
    root.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root.addHandler(console_handler)

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10_485_760, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
        root.addHandler(file_handler)

    # Quieten noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "msal"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
