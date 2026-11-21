from __future__ import annotations

import hashlib
import random
from datetime import datetime, timezone

from dbmonitor_poller_oracle.manifest import MANIFEST
from dbmonitor_sdk.contracts.poller import PollContext
from dbmonitor_sdk.errors import ErrorCategory, PermanentPluginError, TransientPluginError
from dbmonitor_sdk.models.results import CollectorResult, PollResult
from dbmonitor_sdk.models.target import DatabaseTarget


class OraclePollerPlugin:
    plugin_id = MANIFEST.plugin_id
    db_type = MANIFEST.db_type
    manifest = MANIFEST

    def poll(self, target: DatabaseTarget, context: PollContext) -> PollResult:
        creds = context.credentials.resolve(target.secret_ref)
        fault = target.metadata.get("fault_mode", "none")

        if fault == "auth_error":
            raise PermanentPluginError(
                f"ORA-01017 invalid username/password on {target.hostname}",
                category=ErrorCategory.AUTHENTICATION_FAILED,
            )
        if fault == "unreachable":
            raise TransientPluginError(
                f"ORA-12541 TNS:no listener at {target.address}:{target.port}",
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
                            error_message="Deadline exceeded before Oracle collector ran",
                        )
                    )
                    continue

                if fault == "partial_timeout" and group == "sessions":
                    collectors.append(
                        CollectorResult(
                            group=group,
                            status="timeout",
                            error_category=ErrorCategory.QUERY_TIMEOUT.value,
                            error_message="V$SESSION query exceeded deadline",
                        )
                    )
                    continue

                if group == "health":
                    collectors.append(
                        CollectorResult(
                            group="health",
                            status="ok",
                            tables={
                                "instance_health": [
                                    {
                                        "is_available": True,
                                        "response_time_ms": rng.randint(14, 58),
                                        "instance_status": "OPEN",
                                        "open_mode": "READ WRITE",
                                    }
                                ]
                            },
                        )
                    )
                elif group == "sessions":
                    active = rng.randint(18, 95)
                    collectors.append(
                        CollectorResult(
                            group="sessions",
                            status="ok",
                            tables={
                                "active_sessions": [
                                    {
                                        "active_sessions": active,
                                        "blocked_sessions": rng.randint(0, 3),
                                        "total_sessions": active + rng.randint(45, 160),
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
                                "wait_events": [
                                    {
                                        "wait_class": "User I/O",
                                        "total_waits": rng.randint(120_000, 480_000),
                                        "time_waited_ms": rng.randint(8_000, 42_000),
                                    },
                                    {
                                        "wait_class": "Commit",
                                        "total_waits": rng.randint(40_000, 140_000),
                                        "time_waited_ms": rng.randint(2_000, 11_000),
                                    },
                                ]
                            },
                        )
                    )
                elif group == "capacity":
                    collectors.append(
                        CollectorResult(
                            group="capacity",
                            status="ok",
                            tables={
                                "tablespace_usage": [
                                    {
                                        "tablespace_name": "USERS",
                                        "allocated_bytes": 214_748_364_800,
                                        "used_percent": round(rng.uniform(52.0, 84.5), 2),
                                    },
                                    {
                                        "tablespace_name": "ERP_DATA",
                                        "allocated_bytes": 1_099_511_627_776,
                                        "used_percent": round(rng.uniform(61.0, 88.2), 2),
                                    },
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


plugin = OraclePollerPlugin()
