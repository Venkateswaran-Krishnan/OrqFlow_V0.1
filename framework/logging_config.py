from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from framework.state import OrqflowState


LOGGER_NAME = "framework"
DEFAULT_LOGGING_CONFIG: dict[str, Any] = {
    "level": "INFO",
    "log_file": "logs/orqflow.log",
    "console": False,
    "max_bytes": 1_000_000,
    "backup_count": 5,
}


def get_logger(name: str | None = None) -> logging.Logger:
    if name:
        return logging.getLogger(f"{LOGGER_NAME}.{name}")
    return logging.getLogger(LOGGER_NAME)


def configure_logging(config: dict[str, Any] | None = None) -> logging.Logger:
    logging_config = dict(DEFAULT_LOGGING_CONFIG)
    logging_config.update(config or {})

    logger = get_logger()
    logger.setLevel(_get_level(logging_config.get("level")))
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log_file = Path(logging_config["log_file"])
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=int(logging_config["max_bytes"]),
        backupCount=int(logging_config["backup_count"]),
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(_get_level(logging_config.get("level")))
    logger.addHandler(file_handler)

    if logging_config.get("console"):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(_get_level(logging_config.get("level")))
        logger.addHandler(console_handler)

    logger.info("Execution logging started")
    logger.debug("Logging config: %s", logging_config)
    return logger


def shutdown_logging() -> None:
    logger = get_logger()
    logger.info("Execution logging ended")
    for handler in list(logger.handlers):
        handler.flush()
        handler.close()
        logger.removeHandler(handler)


def trace_event(state: OrqflowState, event: str, level: int = logging.INFO, **values: Any) -> None:
    state.setdefault("logs", []).append(event)
    logger = get_logger()
    if values:
        logger.log(level, "%s | %s", event, values)
    else:
        logger.log(level, event)


def _get_level(value: Any) -> int:
    if isinstance(value, int):
        return value
    level = logging.getLevelName(str(value).upper())
    if isinstance(level, int):
        return level
    return logging.INFO
