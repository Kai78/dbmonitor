from __future__ import annotations

import json
import sqlite3
from typing import Any

from dbmonitor_common.identifiers import utc_now_iso
from dbmonitor_common.logging import get_logger
from dbmonitor_platform_db.database import PlatformDatabase
from dbmonitor_results.bundle_loader import BundleStore
from dbmonitor_sdk.errors import SchemaValidationError
from dbmonitor_sdk.validation.metric_envelope import validate_result_envelope
from dbmonitor_sdk.validation.schema_contract import validate_rows_against_json_schema

log = get_logger("results-processor.ingest")


class SchemaNotReadyError(Exception):
    """Raised when incoming message references a schema version ahead of DB."""


def _physical_table(schema_name: str, table_name: str) -> str:
    return f"{schema_name}__{table_name}"


def _coerce_sqlite_val(val: Any) -> Any:
    if isinstance(val, bool):
        return 1 if val else 0
    return val


def process_result_message(
    db: PlatformDatabase,
    bundles: BundleStore,
    payload: dict[str, Any],
) -> None:
    # Handle lightweight started event (LF & manual runs)
    if payload.get("event_type") == "started":
        run_id = payload["polling_run_id"]
        with db.transaction() as conn:
            conn.execute(
                """
                UPDATE platform_polling_runs
                SET status = CASE WHEN status = 'queued' THEN 'running' ELSE status END,
                    started_at = COALESCE(started_at, ?)
                WHERE polling_run_id = ?
                """,
                (payload.get("started_at") or utc_now_iso(), run_id),
            )
        return

    validate_result_envelope(payload)
    run_id = payload["polling_run_id"]
    server_id = payload["server_id"]
    db_type = payload["db_type"]
    plugin_id = payload["plugin_id"]
    schema_version = str(payload["schema_version"])
    collected_at = payload["collected_at"]

    bundle = bundles.get(plugin_id)
    if bundle is None or bundle.db_type != db_type or bundle.schema_name is None:
        raise SchemaValidationError(
            f"Unknown or mismatched bundle '{plugin_id}' for db_type '{db_type}'."
        )

    with db.transaction() as conn:
        run_row = conn.execute(
            "SELECT * FROM platform_polling_runs WHERE polling_run_id = ?",
            (run_id,),
        ).fetchone()
        if run_row is None:
            raise SchemaValidationError(f"Unknown polling_run_id '{run_id}'.")
        if run_row["db_type"] != db_type:
            raise SchemaValidationError(
                f"Run '{run_id}' expected db_type '{run_row['db_type']}', got '{db_type}'."
            )

        # Verify schema readiness (Section 5.7 & 13.2)
        ver_row = conn.execute(
            "SELECT schema_version FROM platform_plugin_schema_versions WHERE namespace = ?",
            (bundle.schema_name,),
        ).fetchone()
        applied_ver = str(ver_row["schema_version"]) if ver_row else "0000"
        if schema_version > applied_ver:
            raise SchemaNotReadyError(
                f"schema_not_ready: message schema_version '{schema_version}' > applied '{applied_ver}'."
            )

        # Validate every collector table & row declaratively against bundle JSON Schemas
        collectors: list[dict[str, Any]] = payload.get("collectors", [])
        inserted_rows = 0
        validation_error: str | None = None

        try:
            for col in collectors:
                if col.get("status") != "ok":
                    continue
                for table_name, rows in col.get("tables", {}).items():
                    if table_name not in bundle.json_schemas:
                        raise SchemaValidationError(
                            f"Undeclared table '{table_name}' for plugin '{plugin_id}'."
                        )
                    jschema = bundle.json_schemas[table_name]
                    validate_rows_against_json_schema(table_name, rows, jschema)

                    phys = _physical_table(bundle.schema_name, table_name)
                    declared_cols = list(jschema["properties"].keys())
                    all_cols = ["server_id", "polling_run_id", "collected_at", *declared_cols]
                    placeholders = ", ".join("?" for _ in all_cols)
                    col_list = ", ".join(all_cols)
                    stmt = f"INSERT OR IGNORE INTO {phys} ({col_list}) VALUES ({placeholders})"

                    for row in rows:
                        values = [server_id, run_id, collected_at] + [
                            _coerce_sqlite_val(row.get(c)) for c in declared_cols
                        ]
                        cur = conn.execute(stmt, values)
                        inserted_rows += cur.rowcount
        except SchemaValidationError as exc:
            validation_error = str(exc)

        final_status = payload["status"]
        err_cat = None
        err_msg = None
        if validation_error is not None:
            final_status = "failed"
            err_cat = "schema_validation_failed"
            err_msg = validation_error
        else:
            failed_cols = [c for c in collectors if c.get("status") != "ok"]
            if failed_cols:
                err_cat = failed_cols[0].get("error_category")
                err_msg = failed_cols[0].get("error_message")

        conn.execute(
            """
            UPDATE platform_polling_runs
            SET status = ?,
                attempt_count = ?,
                started_at = COALESCE(started_at, ?),
                finished_at = ?,
                error_category = ?,
                error_message = ?,
                collectors_json = ?
            WHERE polling_run_id = ?
            """,
            (
                final_status,
                int(payload.get("attempt_count", 1)),
                payload.get("started_at"),
                payload.get("finished_at") or utc_now_iso(),
                err_cat,
                err_msg,
                json.dumps(collectors),
                run_id,
            ),
        )

        # Update polling_state & release lease
        if run_row["assignment_id"]:
            if final_status in ("succeeded", "partially_succeeded"):
                conn.execute(
                    """
                    UPDATE platform_polling_state
                    SET lease_owner = NULL,
                        lease_expires_at = NULL,
                        last_success_at = ?,
                        consecutive_failures = 0
                    WHERE assignment_id = ?
                    """,
                    (payload.get("finished_at") or utc_now_iso(), run_row["assignment_id"]),
                )
            else:
                conn.execute(
                    """
                    UPDATE platform_polling_state
                    SET lease_owner = NULL,
                        lease_expires_at = NULL,
                        consecutive_failures = consecutive_failures + 1
                    WHERE assignment_id = ?
                    """,
                    (run_row["assignment_id"],),
                )

        log.info(
            "result_processed",
            polling_run_id=run_id,
            server_id=server_id,
            pool=payload["pool"],
            status=final_status,
            inserted_rows=inserted_rows,
        )
