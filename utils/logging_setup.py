from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict

from config import Config


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "user_id"):
            log_entry["user_id"] = record.user_id
        if hasattr(record, "ip"):
            log_entry["ip"] = record.ip
        if hasattr(record, "endpoint"):
            log_entry["endpoint"] = record.endpoint
        if hasattr(record, "method"):
            log_entry["method"] = record.method
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            log_entry.update(record.extra)
        return json.dumps(log_entry)


def setup_logger(name: str = "earthscape", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    logger.propagate = False

    log_dir = Path(Config.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    file_formatter = StructuredFormatter()
    file_handler = RotatingFileHandler(
        log_dir / f"{name}.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(level)
    logger.addHandler(file_handler)

    error_handler = RotatingFileHandler(
        log_dir / f"{name}_error.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    error_handler.setFormatter(file_formatter)
    error_handler.setLevel(logging.ERROR)
    logger.addHandler(error_handler)

    auth_handler = RotatingFileHandler(
        log_dir / f"{name}_auth.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    auth_handler.setFormatter(file_formatter)
    auth_handler.setLevel(logging.INFO)
    auth_logger = logging.getLogger(f"{name}.auth")
    auth_logger.addHandler(auth_handler)
    auth_logger.setLevel(logging.INFO)
    auth_logger.propagate = False

    api_handler = RotatingFileHandler(
        log_dir / f"{name}_api.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    api_handler.setFormatter(file_formatter)
    api_handler.setLevel(logging.INFO)
    api_logger = logging.getLogger(f"{name}.api")
    api_logger.addHandler(api_handler)
    api_logger.setLevel(logging.INFO)
    api_logger.propagate = False

    stream_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(stream_formatter)
    stream_handler.setLevel(level)
    logger.addHandler(stream_handler)

    return logger


def get_logger(name: str = "earthscape") -> logging.Logger:
    return logging.getLogger(name)


def log_auth(
    action: str,
    user_id: str | None = None,
    email: str | None = None,
    success: bool = True,
    ip: str | None = None,
    details: Dict[str, Any] | None = None,
) -> None:
    logger = logging.getLogger("earthscape.auth")
    extra: Dict[str, Any] = {"action": action, "success": success}
    if user_id:
        extra["user_id"] = user_id
    if email:
        extra["email"] = email
    if ip:
        extra["ip"] = ip
    if details:
        extra.update(details)
    level = logging.INFO if success else logging.WARNING
    logger.log(level, "Auth: %s %s", action, "success" if success else "failed", extra={"extra": extra})


def log_prediction(
    model: str,
    user_id: str | None = None,
    city: str | None = None,
    result: Dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    logger = logging.getLogger("earthscape")
    extra: Dict[str, Any] = {"model": model, "category": "prediction"}
    if user_id:
        extra["user_id"] = user_id
    if city:
        extra["city"] = city
    if result:
        extra["result"] = result
    if error:
        extra["error"] = error
    level = logging.ERROR if error else logging.INFO
    logger.log(level, "Prediction: %s %s", model, "error" if error else "ok", extra={"extra": extra})


def log_api_request(
    method: str,
    endpoint: str,
    status_code: int,
    response_time_ms: float,
    user_id: str | None = None,
    ip: str | None = None,
    error: str | None = None,
) -> None:
    logger = logging.getLogger("earthscape.api")
    extra: Dict[str, Any] = {
        "method": method,
        "endpoint": endpoint,
        "status_code": status_code,
        "response_time_ms": response_time_ms,
    }
    if user_id:
        extra["user_id"] = user_id
    if ip:
        extra["ip"] = ip
    if error:
        extra["error"] = error
    level = logging.WARNING if status_code >= 400 else logging.INFO
    logger.log(level, "%s %s -> %d", method, endpoint, status_code, extra={"extra": extra})


def log_weather_api(
    action: str,
    endpoint: str,
    success: bool = True,
    response_time_ms: float | None = None,
    error: str | None = None,
    cache_hit: bool = False,
) -> None:
    logger = logging.getLogger("earthscape.api")
    extra: Dict[str, Any] = {
        "category": "weather_api",
        "action": action,
        "endpoint": endpoint,
        "success": success,
        "cache_hit": cache_hit,
    }
    if response_time_ms is not None:
        extra["response_time_ms"] = response_time_ms
    if error:
        extra["error"] = error
    level = logging.ERROR if not success else logging.INFO
    logger.log(level, "Weather API: %s %s", action, "ok" if success else "failed", extra={"extra": extra})


def log_database(
    operation: str,
    collection: str,
    success: bool = True,
    error: str | None = None,
    duration_ms: float | None = None,
) -> None:
    logger = logging.getLogger("earthscape")
    extra: Dict[str, Any] = {
        "category": "database",
        "operation": operation,
        "collection": collection,
        "success": success,
    }
    if duration_ms is not None:
        extra["duration_ms"] = duration_ms
    if error:
        extra["error"] = error
    level = logging.ERROR if not success else logging.DEBUG
    logger.log(level, "DB: %s %s", operation, collection, extra={"extra": extra})
