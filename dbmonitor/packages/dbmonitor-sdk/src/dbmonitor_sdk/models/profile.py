from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    backoff: Literal["none", "exponential"] = "none"
    jitter: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "backoff": self.backoff,
            "jitter": self.jitter,
        }


@dataclass(frozen=True)
class PollingPool:
    name: str
    queue_template: str
    results_queue: str
    expiry_factor: float = 1.0
    celery_pool: str = "threads"
    emit_started_events: bool = False


@dataclass(frozen=True)
class PollingProfile:
    name: str
    pool: str
    interval_seconds: int
    collector_groups: tuple[str, ...]
    timeout_seconds: int
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    max_concurrency_per_server: int = 1
    missed_interval_policy: Literal["skip", "run_once"] = "skip"
    freshness_slo_seconds: int = 150
