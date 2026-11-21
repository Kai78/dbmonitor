from __future__ import annotations

import hashlib
import random
from datetime import datetime, timezone

from dbmonitor_poller_mssql.manifest import MANIFEST
from dbmonitor_sdk.contracts.poller import PollContext
from dbmonitor_sdk.errors import ErrorCategory, PermanentPluginError, TransientPluginError
from dbmonitor_sdk.models.results import CollectorResult, PollResult
from dbmonitor_sdk.models.target import DatabaseTarget


class MssqlPollerPlugin:
    plugin_id = MANIFEST.plugin_id
    db_type = MANIFEST.db_type
    manifest = MANIFEST

    def poll(self, target: DatabaseTarget, context: PollContext) -> PollResult:
        creds = context.credentials.resolve(target.secret_ref)
        fault = target.metadata.get("fault_mode", "none")

        if fault == "auth_error":
            raise PermanentPluginError(
                f"MSSQL Login failed for user '{creds.get('username')}' on {target.hostname}",
                category=ErrorCategory.AUTHENTICATION_FAILED,
            )
        if fault == "unreachable":
            raise TransientPluginError(
                f"MSSQL TCP connection timeout to {target.address}:{target.port}",
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
                            error_message="Deadline exceeded before MSSQL collector ran",
                        )
                    )
                    continue

                if fault == "partial_timeout" and group == "sessions":
                    collectors.append(
                        CollectorResult(
                            group=group,
                            status="timeout",
                            error_category=ErrorCategory.QUERY_TIMEOUT.value,
                            error_message="sys.dm_exec_sessions exceeded lock timeout",
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
                                        "response_time_ms": rng.randint(10, 44),
                                        "product_version": str(target.metadata.get("engine_version", "2022")),
                                        "is_hadr_enabled": True,
                                    }
                                ]
                            },
                        )
                    )
                elif group == "sessions":
                    collectors.append(
                        CollectorResult(
                            group="sessions",
                            status="ok",
                            tables={
                                "user_connections": [
                                    {
                                        "user_connections": rng.randint(25, 145),
                                        "blocked_processes": rng.randint(0, 2),
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
                                "buffer_pool": [
                                    {
                                        "page_life_expectancy_seconds": rng.randint(1800, 9600),
                                        "buffer_cache_hit_percent": round(rng.uniform(98.2, 99.95), 2),
                                    }
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
                                "database_file_sizes": [
                                    {
                                        "database_name": "HR_Core",
                                        "file_type": "ROWS",
                                        "size_bytes": 137_438_953_472,
                                        "used_percent": round(rng.uniform(49.0, 79.0), 2),
                                    },
                                    {
                                        "database_name": "HR_Core",
                                        "file_type": "LOG",
                                        "size_bytes": 34_359_738_368,
                                        "used_percent": round(rng.uniform(12.0, 38.0), 2),
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


plugin = MssqlPollerPlugin()
