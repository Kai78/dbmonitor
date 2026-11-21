from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from dbmonitor_sdk.contracts.manifest import PluginManifest
from dbmonitor_sdk.contracts.poller import PollerPlugin
from dbmonitor_sdk.models.results import PollResult
from dbmonitor_sdk.models.target import DatabaseTarget


class _MockCredentialResolver:
    def resolve(self, secret_ref: str) -> dict[str, str]:
        return {"username": "dbmonitor_ro", "password": "contract-test-password", "secret_ref": secret_ref}


class _MockConnectionProvider:
    def acquire(self, target: DatabaseTarget, credentials: dict[str, str]) -> dict[str, Any]:
        return {"target": target.hostname, "db_type": target.db_type, "simulated": True}

    def release(self, target: DatabaseTarget, conn: Any, broken: bool = False) -> None:
        return None


class _MockPollContext:
    def __init__(self, groups: list[str]) -> None:
        self.run_id = "contract-test-run"
        self.attempt = 1
        self.profile = "high_frequency"
        self.pool = "high_frequency"
        self.collector_groups = groups
        self.deadline = datetime.now(timezone.utc) + timedelta(seconds=15)
        self.connections = _MockConnectionProvider()
        self.credentials = _MockCredentialResolver()


def verify_poller_contract(plugin: PollerPlugin, manifest: PluginManifest) -> list[str]:
    checks: list[str] = []
    assert manifest.kind == "poller", "Poller manifest kind must be 'poller'."
    assert plugin.plugin_id == manifest.plugin_id, "plugin_id mismatch."
    assert plugin.db_type == manifest.db_type, "db_type mismatch."
    checks.append(f"poller identity validated ({plugin.plugin_id} -> {plugin.db_type})")

    target = DatabaseTarget(
        server_id="00000000-0000-0000-0000-000000000001",
        hostname=f"{plugin.db_type}-contract-01.internal",
        address="10.20.0.10",
        port=5432,
        db_type=plugin.db_type,
        environment="staging",
        region="eu-west-1",
        network_zone="default",
        secret_ref=f"secret://dbmonitor/{plugin.db_type}/contract",
        config_version=1,
    )
    ctx = _MockPollContext(list(manifest.collector_groups.keys()))
    result = plugin.poll(target, ctx)
    assert isinstance(result, PollResult), "poll() must return PollResult."
    assert len(result.collectors) == len(manifest.collector_groups), "Must return CollectorResult per requested group."
    for col in result.collectors:
        for table_name, rows in col.tables.items():
            for row in rows:
                assert "server_id" not in row and "polling_run_id" not in row, (
                    f"Plugin table '{table_name}' must not emit envelope columns directly."
                )
    checks.append(f"poll() executed {len(result.collectors)} collector groups with clean engine-only rows")
    return checks
