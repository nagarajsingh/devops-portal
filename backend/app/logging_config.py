from __future__ import annotations

import logging
import os
import sys
from typing import Any

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.getenv(
    "LOG_FORMAT",
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)


def configure_logging() -> None:
    level = getattr(logging, LOG_LEVEL, logging.INFO)
    root_logger = logging.getLogger()

    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root_logger.addHandler(handler)

    root_logger.setLevel(level)

    # Keep useful Uvicorn logs while avoiding duplicate handlers.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).setLevel(level)


configure_logging()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"devops-portal.{name}")


def request_context(request_id: str | None = None, **fields: Any) -> str:
    values: list[str] = []
    if request_id:
        values.append(f"request_id={request_id}")
    values.extend(f"{key}={value}" for key, value in fields.items() if value not in (None, ""))
    return " ".join(values)
