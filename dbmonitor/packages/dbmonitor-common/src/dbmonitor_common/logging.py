from __future__ import annotations

import json
import sys
import threading
from collections import deque
from typing import Any

from dbmonitor_common.identifiers import utc_now_iso

_LOG_BUFFER: deque[dict[str, Any]] = deque(maxlen=500)
_LOG_LOCK = threading.Lock()


class StructuredLogger:
    def __init__(self, service: str) -> None:
        self.service = service

    def log(self, level: str, event: str, **fields: Any) -> None:
        record = {
            "timestamp": utc_now_iso(),
            "level": level.upper(),
            "service": self.service,
            "event": event,
            **{k: v for k, v in fields.items() if v is not None},
        }
        with _LOG_LOCK:
            _LOG_BUFFER.append(record)
        sys.stderr.write(json.dumps(record, default=str) + "\n")
        sys.stderr.flush()

    def info(self, event: str, **fields: Any) -> None:
        self.log("INFO", event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self.log("WARNING", event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self.log("ERROR", event, **fields)


def get_logger(service: str) -> StructuredLogger:
    return StructuredLogger(service)


def get_recent_logs(limit: int = 100, service: str | None = None) -> list[dict[str, Any]]:
    with _LOG_LOCK:
        items = list(_LOG_BUFFER)
    if service:
        items = [item for item in items if item.get("service") == service]
    return list(reversed(items[-limit:]))
