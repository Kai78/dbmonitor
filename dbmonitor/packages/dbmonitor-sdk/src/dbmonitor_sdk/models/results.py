from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class CollectorResult:
    group: str
    status: Literal["ok", "failed", "skipped", "timeout"]
    error_category: str | None = None
    truncated: bool = False
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "status": self.status,
            "error_category": self.error_category,
            "truncated": self.truncated,
            "tables": self.tables,
            "error_message": self.error_message,
        }


@dataclass
class PollResult:
    collected_at: str
    collectors: list[CollectorResult]

    def derive_status(self) -> Literal["succeeded", "partially_succeeded", "failed"]:
        if not self.collectors:
            return "failed"
        statuses = {c.status for c in self.collectors}
        if statuses == {"ok"}:
            return "succeeded"
        if "ok" in statuses:
            return "partially_succeeded"
        return "failed"


@dataclass
class ResultEnvelope:
    message_id: str
    polling_run_id: str
    server_id: str
    db_type: str
    plugin_id: str
    plugin_version: str
    schema_version: str
    profile: str
    pool: str
    attempt_count: int
    collected_at: str
    started_at: str
    finished_at: str
    status: Literal["succeeded", "partially_succeeded", "failed"]
    collectors: list[CollectorResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "polling_run_id": self.polling_run_id,
            "server_id": self.server_id,
            "db_type": self.db_type,
            "plugin_id": self.plugin_id,
            "plugin_version": self.plugin_version,
            "schema_version": self.schema_version,
            "profile": self.profile,
            "pool": self.pool,
            "attempt_count": self.attempt_count,
            "collected_at": self.collected_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "collectors": [c.to_dict() for c in self.collectors],
        }
