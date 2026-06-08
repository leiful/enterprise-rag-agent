# -*- coding: utf-8 -*-

from __future__ import annotations

import contextvars
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import time
from uuid import uuid4

from config import PROJECT_ROOT


LOG_DIR = PROJECT_ROOT / "logs"
APP_LOG_FILE = LOG_DIR / "app.jsonl"
ERROR_LOG_FILE = LOG_DIR / "errors.jsonl"
MAX_LOG_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5

request_id_var = contextvars.ContextVar("request_id", default=None)

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
            "message": record.getMessage(),
        }

        request_id = getattr(record, "request_id", None) or request_id_var.get()
        if request_id:
            payload["request_id"] = request_id

        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(_safe_fields(fields))

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def _safe_fields(fields):
    redacted_keys = {"api_key", "authorization", "password", "token", "cookie", "set_cookie"}
    safe = {}
    for key, value in fields.items():
        normalized_key = str(key).lower()
        if any(secret_key in normalized_key for secret_key in redacted_keys):
            safe[key] = "[REDACTED]"
        else:
            safe[key] = value
    return safe


def configure_logging():
    global _CONFIGURED
    if _CONFIGURED:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = JsonFormatter()
    app_handler = RotatingFileHandler(
        APP_LOG_FILE,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(formatter)
    app_handler._app_json_handler = True

    error_handler = RotatingFileHandler(
        ERROR_LOG_FILE,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    error_handler._app_json_handler = True

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(app_handler)
    root_logger.addHandler(error_handler)

    _CONFIGURED = True


def reset_logging_for_tests():
    global _CONFIGURED
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        if getattr(handler, "_app_json_handler", False):
            root_logger.removeHandler(handler)
            handler.close()
    _CONFIGURED = False


def get_logger(name):
    configure_logging()
    return logging.getLogger(name)


def log_event(logger, level, event, **fields):
    logger.log(level, event, extra={"event": event, "fields": fields})


def new_request_id():
    return uuid4().hex


def set_request_id(request_id):
    return request_id_var.set(request_id)


def reset_request_id(token):
    request_id_var.reset(token)
