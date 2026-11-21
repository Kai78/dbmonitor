from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import timedelta

from dbmonitor_common.identifiers import new_uuid, parse_iso, utc_now, utc_now_iso
from dbmonitor_common.logging import get_logger
from dbmonitor_platform_db.database import PlatformDatabase
from dbmonitor_platform_db.outbox import enqueue_outbox

log = get_logger("scheduler.ticker")


class SchedulerTicker:
    """Claims due polling assignments, pending manual run requests, and due discovery providers."""

    def __init__(self, db: PlatformDatabase, replica_id: str = "scheduler-1", tick_seconds: float = 0.5) -> None:
        self.db = db
        self.replica_id = replica_id
        self.tick_seconds = tick_seconds
        self._stop = threading.Event()

    def _active_server_leases(self, conn: sqlite3.Connection, server_id: str, now_iso: str) -> int:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM platform_polling_state
            WHERE server_id = ? AND lease_expires_at IS NOT NULL AND lease_expires_at > ?
            """,
            (server_id, now_iso),
        ).fetchone()
        return int(row[0])

    def _enqueue_poll_run(
        self,
        conn: sqlite3.Connection,
        *,
        assignment_row: sqlite3.Row | None,
        server_row: sqlite3.Row,
        profile_row: sqlite3.Row,
        pool_row: sqlite3.Row,
        trigger: str,
        requested_by: str | None,
        scheduled_for: str,
        update_schedule: bool,
    ) -> str:
        now = utc_now()
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        db_type = server_row["db_type"]
        pool_name = pool_row["name"]
        run_id = new_uuid()

        # Check plugin registry enablement and pool support
        reg = conn.execute(
            """
            SELECT * FROM platform_plugin_registry
            WHERE kind = 'poller' AND db_type = ? AND enabled = 1
            """,
            (db_type,),
        ).fetchone()
        enabled_pools = json.loads(reg["enabled_pools_json"]) if reg else []
        if reg is None or pool_name not in enabled_pools:
            reason = (
                f"No enabled poller plugin for db_type '{db_type}'"
                if reg is None
                else f"Pool '{pool_name}' is not enabled for db_type '{db_type}'"
            )
            conn.execute(
                """
                INSERT INTO platform_polling_runs (
                    polling_run_id, assignment_id, server_id, db_type, profile_name, pool,
                    collector_groups_json, attempt_count, status, trigger, requested_by,
                    scheduled_for, error_category, error_message, created_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'rejected', ?, ?, ?, 'unknown_plugin', ?, ?, ?)
                """,
                (
                    run_id,
                    assignment_row["assignment_id"] if assignment_row else None,
                    server_row["server_id"],
                    db_type,
                    profile_row["name"],
                    pool_name,
                    profile_row["collector_groups_json"],
                    trigger,
                    requested_by,
                    scheduled_for,
                    reason,
                    now_iso,
                    now_iso,
                ),
            )
            if update_schedule and assignment_row is not None:
                interval_s = int(profile_row["interval_seconds"])
                next_due = (now + timedelta(seconds=interval_s)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                conn.execute(
                    "UPDATE platform_polling_state SET next_due_at = ? WHERE assignment_id = ?",
                    (next_due, assignment_row["assignment_id"]),
                )
            log.warning("poll_run_rejected", polling_run_id=run_id, db_type=db_type, pool=pool_name, reason=reason)
            return run_id

        # Intersect profile collector groups with plugin supported groups
        plugin_groups = set(json.loads(reg["collector_groups_json"] or "{}").keys())
        profile_groups = json.loads(profile_row["collector_groups_json"])
        groups = [g for g in profile_groups if g in plugin_groups]
        if not groups:
            conn.execute(
                """
                INSERT INTO platform_polling_runs (
                    polling_run_id, assignment_id, server_id, db_type, profile_name, pool,
                    collector_groups_json, attempt_count, status, trigger, requested_by,
                    scheduled_for, error_category, error_message, created_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, '[]', 0, 'rejected', ?, ?, ?, 'invalid_configuration', 'Empty collector group intersection', ?, ?)
                """,
                (
                    run_id,
                    assignment_row["assignment_id"] if assignment_row else None,
                    server_row["server_id"],
                    db_type,
                    profile_row["name"],
                    pool_name,
                    trigger,
                    requested_by,
                    scheduled_for,
                    now_iso,
                    now_iso,
                ),
            )
            return run_id

        interval_s = int(profile_row["interval_seconds"])
        expiry_factor = float(pool_row["expiry_factor"])
        timeout_s = int(profile_row["timeout_seconds"])
        expires_dt = now + timedelta(seconds=max(10, int(interval_s * expiry_factor)))
        lease_dt = expires_dt + timedelta(seconds=timeout_s + 10)
        expires_iso = expires_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        lease_iso = lease_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        retry_cfg = json.loads(profile_row["retry_policy_json"] or "{}")
        max_attempts = int(retry_cfg.get("max_attempts", 1))
        queue_name = pool_row["queue_template"].format(
            db_type=db_type,
            zone=server_row["network_zone"] or "default",
        )

        conn.execute(
            """
            INSERT INTO platform_polling_runs (
                polling_run_id, assignment_id, server_id, db_type, profile_name, pool,
                collector_groups_json, attempt_count, status, trigger, requested_by,
                scheduled_for, expires_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'queued', ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                assignment_row["assignment_id"] if assignment_row else None,
                server_row["server_id"],
                db_type,
                profile_row["name"],
                pool_name,
                json.dumps(groups),
                trigger,
                requested_by,
                scheduled_for,
                expires_iso,
                now_iso,
            ),
        )

        if update_schedule and assignment_row is not None:
            prev_due = parse_iso(assignment_row["next_due_at"])
            missed_policy = profile_row["missed_interval_policy"]
            skipped = 0
            if missed_policy == "skip":
                candidate = prev_due + timedelta(seconds=interval_s)
                if candidate <= now:
                    elapsed = (now - prev_due).total_seconds()
                    skipped = max(0, int(elapsed // interval_s))
                    candidate = prev_due + timedelta(seconds=(skipped + 1) * interval_s)
                    if candidate <= now:
                        candidate = now + timedelta(seconds=interval_s)
                next_due_iso = candidate.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            else:
                # run_once: run promptly now, resume interval from now
                next_due_iso = (now + timedelta(seconds=interval_s)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

            conn.execute(
                """
                UPDATE platform_polling_state
                SET next_due_at = ?,
                    lease_owner = ?,
                    lease_expires_at = ?,
                    last_run_id = ?,
                    missed_interval_count = missed_interval_count + ?
                WHERE assignment_id = ?
                """,
                (next_due_iso, self.replica_id, lease_iso, run_id, skipped, assignment_row["assignment_id"]),
            )
        elif assignment_row is not None:
            # Manual run on an existing assignment takes a short lease without changing schedule
            conn.execute(
                """
                UPDATE platform_polling_state
                SET lease_owner = ?, lease_expires_at = ?, last_run_id = ?
                WHERE assignment_id = ?
                """,
                (self.replica_id, lease_iso, run_id, assignment_row["assignment_id"]),
            )

        task_payload = {
            "message_id": new_uuid(),
            "polling_run_id": run_id,
            "server_id": server_row["server_id"],
            "db_type": db_type,
            "profile": profile_row["name"],
            "pool": pool_name,
            "collector_groups": groups,
            "config_version": int(server_row["config_version"]),
            "attempt": 1,
            "max_attempts": max_attempts,
            "scheduled_for": scheduled_for,
            "expires_at": expires_iso,
            "trigger": trigger,
            "requested_by": requested_by,
        }
        enqueue_outbox(conn, queue_name, task_payload, expires_at=expires_iso)
        return run_id

    def _process_manual_requests(self, conn: sqlite3.Connection) -> int:
        pending = conn.execute(
            "SELECT * FROM platform_manual_run_requests WHERE status = 'pending' ORDER BY created_at ASC LIMIT 20"
        ).fetchall()
        processed = 0
        now_iso = utc_now_iso()

        for req in pending:
            scope = json.loads(req["scope_json"])
            run_ids: list[str] = []

            if req["kind"] == "discovery":
                provider_id = scope.get("provider_instance_id")
                where = "enabled = 1"
                params: list = []
                if provider_id:
                    where += " AND provider_instance_id = ?"
                    params.append(provider_id)
                providers = conn.execute(
                    f"SELECT * FROM platform_provider_instances WHERE {where}",
                    params,
                ).fetchall()
                for prov in providers:
                    d_run_id = new_uuid()
                    conn.execute(
                        """
                        INSERT INTO platform_discovery_runs (
                            discovery_run_id, provider_instance_id, provider_name, plugin_id,
                            status, trigger, requested_by, dry_run, created_at
                        ) VALUES (?, ?, ?, ?, 'queued', 'manual', ?, ?, ?)
                        """,
                        (
                            d_run_id,
                            prov["provider_instance_id"],
                            prov["provider_name"],
                            prov["plugin_id"],
                            req["requested_by"],
                            int(req["dry_run"]),
                            now_iso,
                        ),
                    )
                    enqueue_outbox(
                        conn,
                        "discovery.run",
                        {
                            "message_id": new_uuid(),
                            "discovery_run_id": d_run_id,
                            "provider_instance_id": prov["provider_instance_id"],
                            "provider_name": prov["provider_name"],
                            "plugin_id": prov["plugin_id"],
                            "config": json.loads(prov["config_json"] or "{}"),
                            "dry_run": bool(req["dry_run"]),
                            "trigger": "manual",
                            "requested_by": req["requested_by"],
                        },
                    )
                    run_ids.append(d_run_id)
            else:
                # Polling manual request
                sql = "SELECT * FROM platform_database_servers WHERE status = 'active'"
                params = []
                if scope.get("server_id"):
                    sql += " AND server_id = ?"
                    params.append(scope["server_id"])
                if scope.get("server_ids"):
                    placeholders = ",".join("?" for _ in scope["server_ids"])
                    sql += f" AND server_id IN ({placeholders})"
                    params.extend(scope["server_ids"])
                if scope.get("db_type"):
                    sql += " AND db_type = ?"
                    params.append(scope["db_type"])
                if scope.get("environment"):
                    sql += " AND environment = ?"
                    params.append(scope["environment"])
                if scope.get("network_zone"):
                    sql += " AND network_zone = ?"
                    params.append(scope["network_zone"])

                servers = conn.execute(sql, params).fetchall()
                profile_name = scope.get("profile") or "high_frequency"
                profile_row = conn.execute(
                    "SELECT * FROM platform_polling_profiles WHERE name = ?",
                    (profile_name,),
                ).fetchone()
                if profile_row is not None:
                    pool_row = conn.execute(
                        "SELECT * FROM platform_polling_pools WHERE name = ?",
                        (profile_row["pool"],),
                    ).fetchone()
                    if pool_row is not None:
                        for srv in servers:
                            assignment_row = conn.execute(
                                """
                                SELECT * FROM platform_polling_state
                                WHERE server_id = ? AND profile_name = ?
                                """,
                                (srv["server_id"], profile_name),
                            ).fetchone()
                            rid = self._enqueue_poll_run(
                                conn,
                                assignment_row=assignment_row,
                                server_row=srv,
                                profile_row=profile_row,
                                pool_row=pool_row,
                                trigger="manual",
                                requested_by=req["requested_by"],
                                scheduled_for=now_iso,
                                update_schedule=bool(scope.get("advance_schedule", False)),
                            )
                            run_ids.append(rid)

            conn.execute(
                """
                UPDATE platform_manual_run_requests
                SET status = 'dispatched', run_ids_json = ?, processed_at = ?
                WHERE request_id = ?
                """,
                (json.dumps(run_ids), now_iso, req["request_id"]),
            )
            processed += 1
        return processed

    def tick_once(self) -> dict[str, int]:
        now = utc_now()
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        dispatched_polls = 0
        dispatched_discovery = 0
        dispatched_manual = 0

        with self.db.transaction() as conn:
            dispatched_manual = self._process_manual_requests(conn)

            # Claim due polling assignments
            due_states = conn.execute(
                """
                SELECT * FROM platform_polling_state
                WHERE enabled = 1
                  AND next_due_at <= ?
                  AND (lease_expires_at IS NULL OR lease_expires_at < ?)
                ORDER BY next_due_at ASC
                LIMIT 50
                """,
                (now_iso, now_iso),
            ).fetchall()

            for state in due_states:
                srv = conn.execute(
                    "SELECT * FROM platform_database_servers WHERE server_id = ? AND status = 'active'",
                    (state["server_id"],),
                ).fetchone()
                if srv is None:
                    continue
                profile_row = conn.execute(
                    "SELECT * FROM platform_polling_profiles WHERE name = ?",
                    (state["profile_name"],),
                ).fetchone()
                if profile_row is None:
                    continue
                pool_row = conn.execute(
                    "SELECT * FROM platform_polling_pools WHERE name = ?",
                    (profile_row["pool"],),
                ).fetchone()
                if pool_row is None:
                    continue

                # Per-server concurrency limit across all assignments
                active_for_srv = self._active_server_leases(conn, srv["server_id"], now_iso)
                if active_for_srv >= max(2, int(profile_row["max_concurrency_per_server"])):
                    continue

                self._enqueue_poll_run(
                    conn,
                    assignment_row=state,
                    server_row=srv,
                    profile_row=profile_row,
                    pool_row=pool_row,
                    trigger="scheduled",
                    requested_by=None,
                    scheduled_for=state["next_due_at"],
                    update_schedule=True,
                )
                dispatched_polls += 1

            # Claim due provider instances for discovery
            due_providers = conn.execute(
                """
                SELECT * FROM platform_provider_instances
                WHERE enabled = 1
                  AND next_due_at <= ?
                  AND (lease_expires_at IS NULL OR lease_expires_at < ?)
                ORDER BY next_due_at ASC
                LIMIT 10
                """,
                (now_iso, now_iso),
            ).fetchall()

            for prov in due_providers:
                d_run_id = new_uuid()
                interval_s = int(prov["interval_seconds"])
                next_due = (now + timedelta(seconds=interval_s)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                lease_exp = (now + timedelta(seconds=120)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

                conn.execute(
                    """
                    UPDATE platform_provider_instances
                    SET next_due_at = ?, lease_owner = ?, lease_expires_at = ?
                    WHERE provider_instance_id = ?
                    """,
                    (next_due, self.replica_id, lease_exp, prov["provider_instance_id"]),
                )
                conn.execute(
                    """
                    INSERT INTO platform_discovery_runs (
                        discovery_run_id, provider_instance_id, provider_name, plugin_id,
                        status, trigger, requested_by, dry_run, created_at
                    ) VALUES (?, ?, ?, ?, 'queued', 'scheduled', NULL, 0, ?)
                    """,
                    (
                        d_run_id,
                        prov["provider_instance_id"],
                        prov["provider_name"],
                        prov["plugin_id"],
                        now_iso,
                    ),
                )
                enqueue_outbox(
                    conn,
                    "discovery.run",
                    {
                        "message_id": new_uuid(),
                        "discovery_run_id": d_run_id,
                        "provider_instance_id": prov["provider_instance_id"],
                        "provider_name": prov["provider_name"],
                        "plugin_id": prov["plugin_id"],
                        "config": json.loads(prov["config_json"] or "{}"),
                        "dry_run": False,
                        "trigger": "scheduled",
                        "requested_by": None,
                    },
                )
                dispatched_discovery += 1

        return {
            "manual": dispatched_manual,
            "polls": dispatched_polls,
            "discovery": dispatched_discovery,
        }

    def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick_once()
            except Exception as exc:
                log.error("scheduler_tick_error", error=str(exc))
            time.sleep(self.tick_seconds)

    def stop(self) -> None:
        self._stop.set()
