from __future__ import annotations

import hashlib
import random
from datetime import datetime, timezone

from dbmonitor_poller_postgresql.manifest import MANIFEST
from dbmonitor_sdk.contracts.poller import PollContext
from dbmonitor_sdk.errors import ErrorCategory, PermanentPluginError, TransientPluginError
from dbmonitor_sdk.models.results import CollectorResult, PollResult
from dbmonitor_sdk.models.target import DatabaseTarget


class PostgresqlPollerPlugin:
    plugin_id = MANIFEST.plugin_id
    db_type = MANIFEST.db_type
    manifest = MANIFEST

    def poll(self, target: DatabaseTarget, context: PollContext) -> PollResult:
        creds = context.credentials.resolve(target.secret_ref)
        fault = target.metadata.get("fault_mode", "none")

        if fault == "auth_error":
            raise PermanentPluginError(
                f"PostgreSQL authentication failed for {target.hostname}",
                category=ErrorCategory.AUTHENTICATION_FAILED,
            )
        if fault == "unreachable":
            raise TransientPluginError(
                f"PostgreSQL server {target.address}:{target.port} unreachable",
                category=ErrorCategory.TARGET_UNREACHABLE,
            )

        conn = context.connections.acquire(target, creds)
        broken = False
        try:
            seed = int(hashlib.md5(target.server_id.encode()).hexdigest()[:8], 16)
            rng = random.Random(seed + int(datetime.now(timezone.utc).timestamp() // 15))
            collectors: list[CollectorResult] = []
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

            for group in context.collector_groups:
                if datetime.now(timezone.utc) >= context.deadline:
                    collectors.append(
                        CollectorResult(
                            group=group,
                            status="timeout",
                            error_category=ErrorCategory.QUERY_TIMEOUT.value,
                            error_message="Deadline exceeded before collector execution",
                        )
                    )
                    continue

                if fault == "partial_timeout" and group == "sessions":
                    collectors.append(
                        CollectorResult(
                            group=group,
                            status="timeout",
                            error_category=ErrorCategory.QUERY_TIMEOUT.value,
                            error_message="pg_stat_activity query exceeded statement_timeout",
                        )
                    )
                    continue

                if group == "health":
                    latency = rng.randint(6, 38)
                    collectors.append(
                        CollectorResult(
                            group="health",
                            status="ok",
                            tables={
                                "instance_health": [
                                    {
                                        "is_available": True,
                                        "response_time_ms": latency,
                                        "server_version": str(target.metadata.get("engine_version", "16.4")),
                                        "in_recovery": False,
                                    }
                                ]
                            },
                        )
                    )
                elif group == "sessions":
                    active = rng.randint(12, 68)
                    idle = rng.randint(25, 110)
                    waiting = rng.randint(0, 4)
                    row = {
                        "active_connections": active,
                        "idle_connections": idle,
                        "waiting_connections": waiting,
                        "max_connections": 300,
                    }
                    if fault == "bad_schema":
                        row["undeclared_debug_field"] = "bad"
                    collectors.append(
                        CollectorResult(
                            group="sessions",
                            status="ok",
                            tables={"connections": [row]},
                        )
                    )
                elif group == "replication":
                    collectors.append(
                        CollectorResult(
                            group="replication",
                            status="ok",
                            tables={
                                "replication_lag": [
                                    {
                                        "replica_name": f"{target.hostname}-standby-1",
                                        "lag_bytes": rng.randint(0, 16384),
                                        "replay_lag_ms": rng.randint(1, 24),
                                    }
                                ]
                            },
                        )
                    )
                elif group == "performance":
                    collectors.append(
                        CollectorResult(
                            group="performance",
                            status="ok",
                            tables={
                                "table_statistics": [
                                    {
                                        "schema_name": "public",
                                        "table_name": "orders",
                                        "size_bytes": rng.randint(8_000_000_000, 14_000_000_000),
                                        "dead_tuples": rng.randint(1200, 45000),
                                    },
                                    {
                                        "schema_name": "public",
                                        "table_name": "order_events",
                                        "size_bytes": rng.randint(22_000_000_000, 29_000_000_000),
                                        "dead_tuples": rng.randint(500, 18000),
                                    },
                                ]
                            },
                        )
                    )
                elif group == "capacity":
                    used_pct = round(rng.uniform(44.0, 76.5), 2)
                    collectors.append(
                        CollectorResult(
                            group="capacity",
                            status="ok",
                            tables={
                                "database_capacity": [
                                    {
                                        "database_name": "app_primary",
                                        "allocated_bytes": 549_755_813_888,
                                        "used_percent": used_pct,
                                    }
                                ]
                            },
                        )
                    )
            return PollResult(collected_at=now_iso, collectors=collectors)
        except Exception:
            broken = True
            raise
        finally:
            context.connections.release(target, conn, broken=broken)


plugin = PostgresqlPollerPlugin()
