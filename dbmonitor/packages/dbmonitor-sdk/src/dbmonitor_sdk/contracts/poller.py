from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, Sequence

from dbmonitor_sdk.models.results import PollResult
from dbmonitor_sdk.models.target import DatabaseTarget


class CredentialResolver(Protocol):
    def resolve(self, secret_ref: str) -> dict[str, str]:
        """Resolves a secret reference into credentials without logging them."""
        ...


class ConnectionProvider(Protocol):
    def acquire(self, target: DatabaseTarget, credentials: dict[str, str]) -> Any:
        """Obtains a connection (pooled for HF, per-task for LF)."""
        ...

    def release(self, target: DatabaseTarget, conn: Any, broken: bool = False) -> None:
        """Returns or closes a connection."""
        ...


class PollContext(Protocol):
    run_id: str
    attempt: int
    profile: str
    pool: str
    collector_groups: Sequence[str]
    deadline: datetime
    connections: ConnectionProvider
    credentials: CredentialResolver


class PollerPlugin(Protocol):
    plugin_id: str
    db_type: str

    def poll(self, target: DatabaseTarget, context: PollContext) -> PollResult:
        """Collects metrics for the requested collector_groups before deadline."""
        ...
