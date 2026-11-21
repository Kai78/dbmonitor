from __future__ import annotations

import json
import sqlite3
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from dbmonitor_common.broker import RabbitMQBroker
from dbmonitor_common.identifiers import new_uuid, parse_iso, utc_now, utc_now_iso, validate_db_type
from dbmonitor_common.logging import get_logger, get_recent_logs
from dbmonitor_platform_db.database import PlatformDatabase
from dbmonitor_sdk.contracts.manifest import CollectorGroupSpec, PluginManifest
from dbmonitor_sdk.models.profile import PollingProfile, RetryPolicy
from dbmonitor_sdk.validation.profile_rules import validate_profile_against_plugin

log = get_logger("api")


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


class ApiContext:
    def __init__(
        self,
        *,
        db: PlatformDatabase,
        broker: RabbitMQBroker,
        bundle_dir: Path,
        callbacks: dict[str, Callable[..., Any]],
    ) -> None:
        self.db = db
        self.broker = broker
        self.bundle_dir = bundle_dir
        self.callbacks = callbacks


def create_http_server(
    host: str,
    port: int,
    ctx: ApiContext,
) -> ThreadingHTTPServer:
    class RequestHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_json(self, status: int, data: Any) -> None:
            body = json.dumps(data, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            qs = urllib.parse.parse_qs(parsed.query)

            try:
                if path == "/health":
                    self._send_json(200, {"status": "ok", "service": "dbmonitor-api"})
                    return

                if path.startswith("/api/internal/targets/"):
                    server_id = path.split("/")[-1]
                    worker_db_type = self.headers.get("X-Worker-Db-Type", "")
                    if not worker_db_type:
                        self._send_json(401, {"error": "Missing X-Worker-Db-Type header."})
                        return
                    code, payload = ctx.callbacks["get_target_scoped"](server_id, worker_db_type)
                    self._send_json(code, payload)
                    return

                if path == "/api/overview":
                    self._handle_overview()
                    return

                if path == "/api/servers":
                    self._handle_list_servers()
                    return

                if path == "/api/providers":
                    with ctx.db.read() as conn:
                        rows = conn.execute(
                            "SELECT * FROM platform_provider_instances ORDER BY name"
                        ).fetchall()
                    self._send_json(200, {"providers": [_row_to_dict(r) for r in rows]})
                    return

                if path == "/api/rules":
                    with ctx.db.read() as conn:
                        rows = conn.execute(
                            "SELECT * FROM platform_assignment_rules ORDER BY priority ASC"
                        ).fetchall()
                    self._send_json(200, {"rules": [_row_to_dict(r) for r in rows]})
                    return

                if path == "/api/assignments":
                    with ctx.db.read() as conn:
                        rows = conn.execute(
                            """
                            SELECT a.*, s.hostname, s.db_type, s.environment,
                                   st.pool, st.next_due_at, st.lease_owner, st.lease_expires_at,
                                   st.last_run_id, st.last_success_at,
                                   st.consecutive_failures, st.missed_interval_count
                            FROM platform_server_polling_assignments a
                            JOIN platform_database_servers s ON s.server_id = a.server_id
                            LEFT JOIN platform_polling_state st ON st.assignment_id = a.assignment_id
                            ORDER BY s.hostname, a.profile_name
                            """
                        ).fetchall()
                    self._send_json(200, {"assignments": [_row_to_dict(r) for r in rows]})
                    return

                if path == "/api/pools":
                    with ctx.db.read() as conn:
                        rows = conn.execute(
                            "SELECT * FROM platform_polling_pools ORDER BY name"
                        ).fetchall()
                    self._send_json(
                        200,
                        {
                            "pools": [_row_to_dict(r) for r in rows],
                            "queues": ctx.broker.stats(),
                        },
                    )
                    return

                if path == "/api/profiles":
                    with ctx.db.read() as conn:
                        rows = conn.execute(
                            "SELECT * FROM platform_polling_profiles ORDER BY interval_seconds ASC"
                        ).fetchall()
                    self._send_json(200, {"profiles": [_row_to_dict(r) for r in rows]})
                    return

                if path == "/api/discovery-runs":
                    with ctx.db.read() as conn:
                        rows = conn.execute(
                            "SELECT * FROM platform_discovery_runs ORDER BY created_at DESC LIMIT 40"
                        ).fetchall()
                    self._send_json(200, {"runs": [_row_to_dict(r) for r in rows]})
                    return

                if path.startswith("/api/discovery-runs/"):
                    run_id = path.split("/")[-1]
                    with ctx.db.read() as conn:
                        row = conn.execute(
                            "SELECT * FROM platform_discovery_runs WHERE discovery_run_id = ?",
                            (run_id,),
                        ).fetchone()
                    if row is None:
                        self._send_json(404, {"error": "Discovery run not found."})
                    else:
                        self._send_json(200, _row_to_dict(row))
                    return

                if path == "/api/polling-runs":
                    limit = int(qs.get("limit", ["60"])[0])
                    status_f = qs.get("status", [None])[0]
                    pool_f = qs.get("pool", [None])[0]
                    db_type_f = qs.get("db_type", [None])[0]
                    where = ["1=1"]
                    params: list[Any] = []
                    if status_f:
                        where.append("r.status = ?")
                        params.append(status_f)
                    if pool_f:
                        where.append("r.pool = ?")
                        params.append(pool_f)
                    if db_type_f:
                        where.append("r.db_type = ?")
                        params.append(db_type_f)
                    params.append(limit)
                    with ctx.db.read() as conn:
                        runs = conn.execute(
                            f"""
                            SELECT r.*, s.hostname
                            FROM platform_polling_runs r
                            LEFT JOIN platform_database_servers s ON s.server_id = r.server_id
                            WHERE {' AND '.join(where)}
                            ORDER BY r.created_at DESC
                            LIMIT ?
                            """,
                            params,
                        ).fetchall()
                        manual_reqs = conn.execute(
                            "SELECT * FROM platform_manual_run_requests ORDER BY created_at DESC LIMIT 20"
                        ).fetchall()
                        outbox = conn.execute(
                            "SELECT * FROM platform_outbox ORDER BY created_at DESC LIMIT 30"
                        ).fetchall()
                    self._send_json(
                        200,
                        {
                            "runs": [_row_to_dict(r) for r in runs],
                            "manual_requests": [_row_to_dict(r) for r in manual_reqs],
                            "outbox": [_row_to_dict(r) for r in outbox],
                        },
                    )
                    return

                if path.startswith("/api/polling-runs/"):
                    run_id = path.split("/")[-1]
                    with ctx.db.read() as conn:
                        row = conn.execute(
                            "SELECT * FROM platform_polling_runs WHERE polling_run_id = ?",
                            (run_id,),
                        ).fetchone()
                    if row is None:
                        self._send_json(404, {"error": "Polling run not found."})
                    else:
                        self._send_json(200, _row_to_dict(row))
                    return

                if path == "/api/dlq":
                    self._send_json(200, {"messages": ctx.broker.peek_dlq()})
                    return

                if path == "/api/plugins":
                    self._handle_plugins()
                    return

                if path == "/api/reporting/health":
                    with ctx.db.read() as conn:
                        rows = conn.execute(
                            """
                            SELECT r.db_type, r.server_id, s.hostname, s.environment,
                                   r.polling_run_id, r.collected_at, r.is_available, r.response_time_ms
                            FROM reporting_instance_health r
                            JOIN platform_database_servers s ON s.server_id = r.server_id
                            ORDER BY r.collected_at DESC
                            LIMIT 100
                            """
                        ).fetchall()
                    self._send_json(200, {"rows": [_row_to_dict(r) for r in rows]})
                    return

                if path.startswith("/api/metrics/"):
                    parts = path.strip("/").split("/")
                    if len(parts) == 4:
                        _, _, db_type, table_name = parts
                        self._handle_metric_table(db_type, table_name)
                        return

                if path == "/api/logs":
                    service = qs.get("service", [None])[0]
                    self._send_json(200, {"logs": get_recent_logs(limit=100, service=service)})
                    return

                if path == "/api/audit":
                    with ctx.db.read() as conn:
                        rows = conn.execute(
                            "SELECT * FROM platform_audit_log ORDER BY created_at DESC LIMIT 50"
                        ).fetchall()
                    self._send_json(200, {"audit": [_row_to_dict(r) for r in rows]})
                    return

                self._send_json(404, {"error": f"Unknown endpoint {path}"})
            except Exception as exc:
                log.error("api_get_error", path=path, error=str(exc))
                self._send_json(500, {"error": str(exc)})

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            try:
                body = self._read_json()

                if path == "/api/polling-runs":
                    self._handle_manual_polling_trigger(body)
                    return

                if path.startswith("/api/polling-runs/") and path.endswith("/cancel"):
                    run_id = path.split("/")[-2]
                    self._handle_cancel_run(run_id, body)
                    return

                if path.startswith("/api/polling-runs/") and path.endswith("/retry"):
                    run_id = path.split("/")[-2]
                    self._handle_retry_polling_run(run_id, body)
                    return

                if path == "/api/discovery-runs":
                    self._handle_manual_discovery_trigger(body)
                    return

                if path.startswith("/api/discovery-runs/") and path.endswith("/retry"):
                    run_id = path.split("/")[-2]
                    self._handle_retry_discovery_run(run_id, body)
                    return

                if path.startswith("/api/servers/") and path.endswith("/fault-mode"):
                    server_id = path.split("/")[-2]
                    self._handle_set_fault_mode(server_id, body)
                    return

                if path == "/api/profiles":
                    self._handle_create_profile(body)
                    return

                if path == "/api/assignments":
                    self._handle_create_assignment(body)
                    return

                if path == "/api/rules":
                    self._handle_create_rule(body)
                    return

                if path == "/api/providers":
                    self._handle_create_provider(body)
                    return

                if path.startswith("/api/queues/") and path.endswith("/pause"):
                    qname = urllib.parse.unquote(path.split("/")[-2])
                    ctx.broker.pause_queue(qname)
                    self._send_json(200, {"queue": qname, "paused": True})
                    return

                if path.startswith("/api/queues/") and path.endswith("/resume"):
                    qname = urllib.parse.unquote(path.split("/")[-2])
                    ctx.broker.resume_queue(qname)
                    self._send_json(200, {"queue": qname, "paused": False})
                    return

                if path.startswith("/api/dlq/") and path.endswith("/drain"):
                    dlq_name = urllib.parse.unquote(path.split("/")[-2])
                    drained = ctx.broker.drain_dlq(dlq_name)
                    self._send_json(200, {"queue": dlq_name, "drained": drained})
                    return

                if path == "/api/ci/verify":
                    report = ctx.callbacks["run_ci_checks"]()
                    self._send_json(200, report)
                    return

                if path == "/api/maintenance/run":
                    res = ctx.callbacks["run_maintenance"]()
                    self._send_json(200, res)
                    return

                self._send_json(404, {"error": f"Unknown endpoint {path}"})
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
            except Exception as exc:
                log.error("api_post_error", path=path, error=str(exc))
                self._send_json(500, {"error": str(exc)})

        def do_PATCH(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            try:
                body = self._read_json()
                if path.startswith("/api/plugins/"):
                    plugin_id = path.split("/")[-1]
                    self._handle_update_plugin(plugin_id, body)
                    return
                if path.startswith("/api/assignments/"):
                    assignment_id = path.split("/")[-1]
                    enabled = 1 if body.get("enabled", True) else 0
                    with ctx.db.transaction() as conn:
                        conn.execute(
                            "UPDATE platform_server_polling_assignments SET enabled = ? WHERE assignment_id = ?",
                            (enabled, assignment_id),
                        )
                        conn.execute(
                            "UPDATE platform_polling_state SET enabled = ? WHERE assignment_id = ?",
                            (enabled, assignment_id),
                        )
                    self._send_json(200, {"assignment_id": assignment_id, "enabled": bool(enabled)})
                    return
                self._send_json(404, {"error": f"Unknown endpoint {path}"})
            except Exception as exc:
                self._send_json(500, {"error": str(exc)})

        def _handle_overview(self) -> None:
            now = utc_now()
            with ctx.db.read() as conn:
                servers_total = conn.execute(
                    "SELECT COUNT(*) FROM platform_database_servers WHERE status = 'active'"
                ).fetchone()[0]
                assignments_total = conn.execute(
                    "SELECT COUNT(*) FROM platform_polling_state WHERE enabled = 1"
                ).fetchone()[0]
                outbox_pending = conn.execute(
                    "SELECT COUNT(*) FROM platform_outbox WHERE published_at IS NULL"
                ).fetchone()[0]
                runs_by_status = {
                    r["status"]: r["cnt"]
                    for r in conn.execute(
                        "SELECT status, COUNT(*) AS cnt FROM platform_polling_runs GROUP BY status"
                    ).fetchall()
                }
                freshness_rows = conn.execute(
                    """
                    SELECT st.assignment_id, st.server_id, s.hostname, st.db_type, st.profile_name,
                           st.pool, st.last_success_at, st.consecutive_failures, st.missed_interval_count,
                           p.interval_seconds, p.freshness_slo_seconds
                    FROM platform_polling_state st
                    JOIN platform_database_servers s ON s.server_id = st.server_id
                    JOIN platform_polling_profiles p ON p.name = st.profile_name
                    WHERE st.enabled = 1 AND s.status = 'active'
                    ORDER BY s.hostname, st.profile_name
                    """
                ).fetchall()

            slo_items: list[dict[str, Any]] = []
            slo_breaches = 0
            for row in freshness_rows:
                staleness_s = None
                slo_ok = True
                if row["last_success_at"]:
                    staleness_s = round((now - parse_iso(row["last_success_at"])).total_seconds(), 1)
                    slo_ok = staleness_s <= int(row["freshness_slo_seconds"])
                else:
                    slo_ok = False
                if not slo_ok:
                    slo_breaches += 1
                slo_items.append(
                    {
                        **_row_to_dict(row),
                        "staleness_seconds": staleness_s,
                        "slo_compliant": slo_ok,
                    }
                )

            queues = ctx.broker.stats()
            dlq_depth = sum(q["depth"] for q in queues if q["is_dlq"])

            self._send_json(
                200,
                {
                    "summary": {
                        "active_servers": servers_total,
                        "active_assignments": assignments_total,
                        "outbox_pending": outbox_pending,
                        "dlq_depth": dlq_depth,
                        "slo_breaches": slo_breaches,
                        "runs_by_status": runs_by_status,
                    },
                    "freshness": slo_items,
                    "queues": queues,
                    "workers": ctx.callbacks["get_worker_statuses"](),
                    "processors": ctx.callbacks["get_processor_statuses"](),
                },
            )

        def _handle_list_servers(self) -> None:
            with ctx.db.read() as conn:
                servers = conn.execute(
                    "SELECT * FROM platform_database_servers ORDER BY environment, db_type, hostname"
                ).fetchall()
                assocs = conn.execute(
                    """
                    SELECT pa.*, pi.name AS provider_instance_name
                    FROM platform_provider_associations pa
                    JOIN platform_provider_instances pi ON pi.provider_instance_id = pa.provider_instance_id
                    """
                ).fetchall()
                states = conn.execute(
                    "SELECT * FROM platform_polling_state"
                ).fetchall()
                latest_health = {}
                try:
                    for h in conn.execute(
                        """
                        SELECT r.server_id, r.is_available, r.response_time_ms, r.collected_at
                        FROM reporting_instance_health r
                        INNER JOIN (
                            SELECT server_id, MAX(collected_at) AS max_ts
                            FROM reporting_instance_health
                            GROUP BY server_id
                        ) m ON m.server_id = r.server_id AND m.max_ts = r.collected_at
                        """
                    ).fetchall():
                        latest_health[h["server_id"]] = _row_to_dict(h)
                except sqlite3.OperationalError:
                    pass

            assoc_by_srv: dict[str, list[dict]] = {}
            for a in assocs:
                assoc_by_srv.setdefault(a["server_id"], []).append(_row_to_dict(a))

            states_by_srv: dict[str, list[dict]] = {}
            for st in states:
                states_by_srv.setdefault(st["server_id"], []).append(_row_to_dict(st))

            result = []
            for s in servers:
                d = _row_to_dict(s)
                d["tags"] = json.loads(d["tags_json"] or "{}")
                d["metadata"] = json.loads(d["metadata_json"] or "{}")
                d["providers"] = assoc_by_srv.get(s["server_id"], [])
                d["polling_states"] = states_by_srv.get(s["server_id"], [])
                d["latest_health"] = latest_health.get(s["server_id"])
                result.append(d)
            self._send_json(200, {"servers": result})

        def _handle_manual_polling_trigger(self, body: dict[str, Any]) -> None:
            requested_by = body.get("requested_by") or "operator@dbmonitor"
            idempotency_key = body.get("idempotency_key") or None
            scope = {
                "server_id": body.get("server_id"),
                "server_ids": body.get("server_ids"),
                "db_type": body.get("db_type"),
                "environment": body.get("environment"),
                "network_zone": body.get("network_zone"),
                "profile": body.get("profile") or "high_frequency",
                "advance_schedule": bool(body.get("advance_schedule", False)),
            }
            if scope["db_type"]:
                validate_db_type(scope["db_type"])

            with ctx.db.transaction() as conn:
                if idempotency_key:
                    existing = conn.execute(
                        "SELECT * FROM platform_manual_run_requests WHERE idempotency_key = ?",
                        (idempotency_key,),
                    ).fetchone()
                    if existing is not None:
                        self._send_json(
                            HTTPStatus.ACCEPTED,
                            {
                                "request_id": existing["request_id"],
                                "status": existing["status"],
                                "idempotent_replay": True,
                            },
                        )
                        return

                request_id = new_uuid()
                now_iso = utc_now_iso()
                conn.execute(
                    """
                    INSERT INTO platform_manual_run_requests (
                        request_id, idempotency_key, kind, scope_json,
                        requested_by, dry_run, status, run_ids_json, created_at
                    ) VALUES (?, ?, 'polling', ?, ?, 0, 'pending', '[]', ?)
                    """,
                    (request_id, idempotency_key, json.dumps(scope), requested_by, now_iso),
                )
                conn.execute(
                    """
                    INSERT INTO platform_audit_log (
                        audit_id, actor, action, target_type, target_id, details_json, created_at
                    ) VALUES (?, ?, 'manual_poll_request', 'polling_scope', ?, ?, ?)
                    """,
                    (new_uuid(), requested_by, request_id, json.dumps(scope), now_iso),
                )

            self._send_json(
                HTTPStatus.ACCEPTED,
                {
                    "request_id": request_id,
                    "status": "requested",
                    "scope": scope,
                },
            )

        def _handle_cancel_run(self, run_id: str, body: dict[str, Any]) -> None:
            actor = body.get("requested_by") or "operator@dbmonitor"
            now_iso = utc_now_iso()
            with ctx.db.transaction() as conn:
                row = conn.execute(
                    "SELECT * FROM platform_polling_runs WHERE polling_run_id = ?",
                    (run_id,),
                ).fetchone()
                if row is None:
                    self._send_json(404, {"error": "Polling run not found."})
                    return
                if row["status"] != "queued":
                    self._send_json(
                        409,
                        {
                            "error": (
                                f"Cannot cancel run in status '{row['status']}'. "
                                "Cancellation applies only to queued runs."
                            )
                        },
                    )
                    return
                queue_name = f"poll.{row['db_type']}.{row['pool']}"
                ctx.broker.revoke_matching(queue_name, run_id)
                conn.execute(
                    """
                    UPDATE platform_polling_runs
                    SET status = 'cancelled', finished_at = ?
                    WHERE polling_run_id = ?
                    """,
                    (now_iso, run_id),
                )
                if row["assignment_id"]:
                    conn.execute(
                        """
                        UPDATE platform_polling_state
                        SET lease_owner = NULL, lease_expires_at = NULL
                        WHERE assignment_id = ?
                        """,
                        (row["assignment_id"],),
                    )
                conn.execute(
                    """
                    INSERT INTO platform_audit_log (
                        audit_id, actor, action, target_type, target_id, details_json, created_at
                    ) VALUES (?, ?, 'cancel_polling_run', 'polling_run', ?, '{}', ?)
                    """,
                    (new_uuid(), actor, run_id, now_iso),
                )
            self._send_json(200, {"polling_run_id": run_id, "status": "cancelled"})

        def _handle_retry_polling_run(self, run_id: str, body: dict[str, Any]) -> None:
            with ctx.db.read() as conn:
                row = conn.execute(
                    "SELECT * FROM platform_polling_runs WHERE polling_run_id = ?",
                    (run_id,),
                ).fetchone()
            if row is None:
                self._send_json(404, {"error": "Polling run not found."})
                return
            self._handle_manual_polling_trigger(
                {
                    "server_id": row["server_id"],
                    "profile": row["profile_name"],
                    "requested_by": body.get("requested_by") or "operator@dbmonitor",
                }
            )

        def _handle_manual_discovery_trigger(self, body: dict[str, Any]) -> None:
            requested_by = body.get("requested_by") or "operator@dbmonitor"
            dry_run = bool(body.get("dry_run", False))
            scope = {"provider_instance_id": body.get("provider_instance_id")}
            request_id = new_uuid()
            now_iso = utc_now_iso()
            with ctx.db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO platform_manual_run_requests (
                        request_id, idempotency_key, kind, scope_json,
                        requested_by, dry_run, status, run_ids_json, created_at
                    ) VALUES (?, ?, 'discovery', ?, ?, ?, 'pending', '[]', ?)
                    """,
                    (
                        request_id,
                        body.get("idempotency_key"),
                        json.dumps(scope),
                        requested_by,
                        1 if dry_run else 0,
                        now_iso,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO platform_audit_log (
                        audit_id, actor, action, target_type, target_id, details_json, created_at
                    ) VALUES (?, ?, 'manual_discovery_request', 'discovery_scope', ?, ?, ?)
                    """,
                    (new_uuid(), requested_by, request_id, json.dumps({**scope, "dry_run": dry_run}), now_iso),
                )
            self._send_json(
                HTTPStatus.ACCEPTED,
                {"request_id": request_id, "status": "requested", "dry_run": dry_run},
            )

        def _handle_retry_discovery_run(self, run_id: str, body: dict[str, Any]) -> None:
            with ctx.db.read() as conn:
                row = conn.execute(
                    "SELECT * FROM platform_discovery_runs WHERE discovery_run_id = ?",
                    (run_id,),
                ).fetchone()
            if row is None:
                self._send_json(404, {"error": "Discovery run not found."})
                return
            self._handle_manual_discovery_trigger(
                {
                    "provider_instance_id": row["provider_instance_id"],
                    "dry_run": bool(row["dry_run"]),
                    "requested_by": body.get("requested_by") or "operator@dbmonitor",
                }
            )

        def _handle_set_fault_mode(self, server_id: str, body: dict[str, Any]) -> None:
            fault_mode = body.get("fault_mode", "none")
            with ctx.db.transaction() as conn:
                row = conn.execute(
                    "SELECT metadata_json FROM platform_database_servers WHERE server_id = ?",
                    (server_id,),
                ).fetchone()
                if row is None:
                    self._send_json(404, {"error": "Server not found."})
                    return
                meta = json.loads(row["metadata_json"] or "{}")
                meta["fault_mode"] = fault_mode
                conn.execute(
                    """
                    UPDATE platform_database_servers
                    SET metadata_json = ?, config_version = config_version + 1, updated_at = ?
                    WHERE server_id = ?
                    """,
                    (json.dumps(meta), utc_now_iso(), server_id),
                )
            self._send_json(200, {"server_id": server_id, "fault_mode": fault_mode})

        def _handle_create_profile(self, body: dict[str, Any]) -> None:
            name = str(body.get("name", "")).strip()
            pool = str(body.get("pool", "high_frequency")).strip()
            interval_s = int(body.get("interval_seconds", 60))
            groups = tuple(body.get("collector_groups", []))
            timeout_s = int(body.get("timeout_seconds", 20))
            missed_policy = str(body.get("missed_interval_policy", "skip"))
            slo_s = int(body.get("freshness_slo_seconds", interval_s * 2 + 30))

            if not name or not groups:
                raise ValueError("Profile name and collector_groups are required.")

            profile = PollingProfile(
                name=name,
                pool=pool,
                interval_seconds=interval_s,
                collector_groups=groups,
                timeout_seconds=timeout_s,
                retry=RetryPolicy(
                    max_attempts=1 if pool == "high_frequency" else 3,
                    backoff="none" if pool == "high_frequency" else "exponential",
                    jitter=(pool != "high_frequency"),
                ),
                missed_interval_policy=missed_policy,  # type: ignore[arg-type]
                freshness_slo_seconds=slo_s,
            )

            # Enforce floor against all registered enabled pollers that support any of the groups
            with ctx.db.transaction() as conn:
                pollers = conn.execute(
                    "SELECT * FROM platform_plugin_registry WHERE kind = 'poller' AND enabled = 1"
                ).fetchall()
                validated_any = False
                for p in pollers:
                    raw_groups = json.loads(p["collector_groups_json"] or "{}")
                    if not any(g in raw_groups for g in groups):
                        continue
                    manifest = PluginManifest(
                        plugin_id=p["plugin_id"],
                        kind="poller",
                        version=p["version"],
                        sdk_range=">=1.0,<2.0",
                        db_type=p["db_type"],
                        collector_groups={
                            gn: CollectorGroupSpec(
                                min_interval_seconds=int(gs["min_interval_seconds"]),
                                default_timeout_seconds=int(gs["default_timeout_seconds"]),
                            )
                            for gn, gs in raw_groups.items()
                        },
                    )
                    validate_profile_against_plugin(profile, manifest)
                    validated_any = True
                if not validated_any:
                    raise ValueError("No registered poller supports any of the requested collector_groups.")

                conn.execute(
                    """
                    INSERT INTO platform_polling_profiles (
                        name, pool, interval_seconds, collector_groups_json, timeout_seconds,
                        retry_policy_json, max_concurrency_per_server, missed_interval_policy,
                        freshness_slo_seconds, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                    """,
                    (
                        name,
                        pool,
                        interval_s,
                        json.dumps(list(groups)),
                        timeout_s,
                        json.dumps(profile.retry.to_dict()),
                        missed_policy,
                        slo_s,
                        utc_now_iso(),
                    ),
                )
            self._send_json(201, {"name": name, "pool": pool, "interval_seconds": interval_s})

        def _handle_create_assignment(self, body: dict[str, Any]) -> None:
            server_id = body.get("server_id")
            profile_name = body.get("profile_name")
            if not server_id or not profile_name:
                raise ValueError("server_id and profile_name are required.")
            with ctx.db.transaction() as conn:
                srv = conn.execute(
                    "SELECT * FROM platform_database_servers WHERE server_id = ?",
                    (server_id,),
                ).fetchone()
                prof = conn.execute(
                    "SELECT * FROM platform_polling_profiles WHERE name = ?",
                    (profile_name,),
                ).fetchone()
                if srv is None or prof is None:
                    raise ValueError("Server or profile not found.")

                reg = conn.execute(
                    "SELECT * FROM platform_plugin_registry WHERE kind = 'poller' AND db_type = ? AND enabled = 1",
                    (srv["db_type"],),
                ).fetchone()
                if reg is None:
                    raise ValueError(f"No enabled poller for db_type '{srv['db_type']}'.")
                raw_groups = json.loads(reg["collector_groups_json"] or "{}")
                manifest = PluginManifest(
                    plugin_id=reg["plugin_id"],
                    kind="poller",
                    version=reg["version"],
                    sdk_range=">=1.0,<2.0",
                    db_type=reg["db_type"],
                    collector_groups={
                        gn: CollectorGroupSpec(
                            min_interval_seconds=int(gs["min_interval_seconds"]),
                            default_timeout_seconds=int(gs["default_timeout_seconds"]),
                        )
                        for gn, gs in raw_groups.items()
                    },
                )
                profile_obj = PollingProfile(
                    name=prof["name"],
                    pool=prof["pool"],
                    interval_seconds=int(prof["interval_seconds"]),
                    collector_groups=tuple(json.loads(prof["collector_groups_json"])),
                    timeout_seconds=int(prof["timeout_seconds"]),
                )
                validate_profile_against_plugin(profile_obj, manifest)

                aid = new_uuid()
                now_iso = utc_now_iso()
                conn.execute(
                    """
                    INSERT INTO platform_server_polling_assignments (
                        assignment_id, server_id, profile_name, source,
                        concurrency_group, overrides_json, enabled, created_at
                    ) VALUES (?, ?, ?, 'manual', ?, '{}', 1, ?)
                    """,
                    (aid, server_id, profile_name, body.get("concurrency_group"), now_iso),
                )
                conn.execute(
                    """
                    INSERT INTO platform_polling_state (
                        assignment_id, server_id, profile_name, db_type, pool,
                        enabled, next_due_at, lease_owner, lease_expires_at,
                        last_run_id, last_success_at, consecutive_failures, missed_interval_count
                    ) VALUES (?, ?, ?, ?, ?, 1, ?, NULL, NULL, NULL, NULL, 0, 0)
                    """,
                    (aid, server_id, profile_name, srv["db_type"], prof["pool"], now_iso),
                )
            self._send_json(201, {"assignment_id": aid, "source": "manual"})

        def _handle_create_rule(self, body: dict[str, Any]) -> None:
            name = str(body.get("name", "")).strip()
            profile_names = body.get("profile_names", [])
            if not name or not profile_names:
                raise ValueError("Rule name and profile_names are required.")
            rid = new_uuid()
            with ctx.db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO platform_assignment_rules (
                        rule_id, name, db_type, environment, network_zone,
                        tag_filter_json, profile_names_json, priority, enabled, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        rid,
                        name,
                        body.get("db_type") or None,
                        body.get("environment") or None,
                        body.get("network_zone") or None,
                        json.dumps(body["tag_filter"]) if body.get("tag_filter") else None,
                        json.dumps(profile_names),
                        int(body.get("priority", 50)),
                        utc_now_iso(),
                    ),
                )
            self._send_json(201, {"rule_id": rid})

        def _handle_create_provider(self, body: dict[str, Any]) -> None:
            name = str(body.get("name", "")).strip()
            plugin_id = str(body.get("plugin_id", "dbmonitor-provider-cmdb")).strip()
            provider_name = plugin_id.removeprefix("dbmonitor-provider-")
            if not name:
                raise ValueError("Provider instance name is required.")
            pid = new_uuid()
            now_iso = utc_now_iso()
            with ctx.db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO platform_provider_instances (
                        provider_instance_id, name, plugin_id, provider_name,
                        credentials_ref, config_json, interval_seconds,
                        next_due_at, enabled, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        pid,
                        name,
                        plugin_id,
                        provider_name,
                        body.get("credentials_ref") or f"secret://vault/providers/{name}",
                        json.dumps(body.get("config", {})),
                        int(body.get("interval_seconds", 300)),
                        now_iso,
                        now_iso,
                    ),
                )
            self._send_json(201, {"provider_instance_id": pid, "name": name})

        def _handle_plugins(self) -> None:
            with ctx.db.read() as conn:
                plugins = conn.execute(
                    "SELECT * FROM platform_plugin_registry ORDER BY kind, plugin_id"
                ).fetchall()
                schemas = conn.execute(
                    "SELECT * FROM platform_plugin_schema_versions ORDER BY namespace"
                ).fetchall()

            bundle_details: dict[str, Any] = {}
            for p in plugins:
                bpath = Path(p["bundle_path"])
                detail: dict[str, Any] = {"files": []}
                if bpath.exists():
                    detail["files"] = [
                        str(fp.relative_to(bpath))
                        for fp in sorted(bpath.rglob("*"))
                        if fp.is_file()
                    ]
                    sfile = bpath / "schema_manifest.json"
                    if sfile.exists():
                        detail["schema_manifest"] = json.loads(sfile.read_text(encoding="utf-8"))
                    migs = bpath / "migrations"
                    if migs.exists():
                        detail["migrations"] = {
                            mf.name: mf.read_text(encoding="utf-8")
                            for mf in sorted(migs.glob("*.sql"))
                        }
                bundle_details[p["plugin_id"]] = detail

            self._send_json(
                200,
                {
                    "plugins": [_row_to_dict(r) for r in plugins],
                    "schema_versions": [_row_to_dict(r) for r in schemas],
                    "bundles": bundle_details,
                },
            )

        def _handle_update_plugin(self, plugin_id: str, body: dict[str, Any]) -> None:
            with ctx.db.transaction() as conn:
                row = conn.execute(
                    "SELECT * FROM platform_plugin_registry WHERE plugin_id = ?",
                    (plugin_id,),
                ).fetchone()
                if row is None:
                    self._send_json(404, {"error": "Plugin not found."})
                    return
                enabled = 1 if body.get("enabled", bool(row["enabled"])) else 0
                pools = body.get("enabled_pools", json.loads(row["enabled_pools_json"]))
                conn.execute(
                    """
                    UPDATE platform_plugin_registry
                    SET enabled = ?, enabled_pools_json = ?, updated_at = ?
                    WHERE plugin_id = ?
                    """,
                    (enabled, json.dumps(pools), utc_now_iso(), plugin_id),
                )
            self._send_json(200, {"plugin_id": plugin_id, "enabled": bool(enabled), "enabled_pools": pools})

        def _handle_metric_table(self, db_type: str, table_name: str) -> None:
            validate_db_type(db_type)
            phys = f"metrics_{db_type}__{table_name}"
            with ctx.db.read() as conn:
                exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
                    (phys,),
                ).fetchone()
                if exists is None:
                    self._send_json(404, {"error": f"Metric table '{phys}' not found."})
                    return
                rows = conn.execute(
                    f"""
                    SELECT m.*, s.hostname
                    FROM {phys} m
                    LEFT JOIN platform_database_servers s ON s.server_id = m.server_id
                    ORDER BY m.collected_at DESC
                    LIMIT 80
                    """
                ).fetchall()
                partitions = conn.execute(
                    """
                    SELECT * FROM platform_partition_catalog
                    WHERE schema_name = ? AND table_name = ?
                    ORDER BY range_start DESC
                    """,
                    (f"metrics_{db_type}", table_name),
                ).fetchall()
            self._send_json(
                200,
                {
                    "table": f"metrics_{db_type}.{table_name}",
                    "rows": [_row_to_dict(r) for r in rows],
                    "partitions": [_row_to_dict(p) for p in partitions],
                },
            )

    return ThreadingHTTPServer((host, port), RequestHandler)
