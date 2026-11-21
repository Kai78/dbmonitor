from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from dbmonitor_common.identifiers import new_uuid, utc_now_iso
from dbmonitor_common.logging import get_logger
from dbmonitor_platform_db.database import PlatformDatabase
from dbmonitor_sdk.contracts.schema import SchemaManifest
from dbmonitor_sdk.validation.schema_contract import validate_schema_manifest

log = get_logger("schema-migrator.plugin_runner")

_SQLITE_TYPE_MAP = {
    "boolean": "INTEGER",
    "integer": "INTEGER",
    "bigint": "INTEGER",
    "double": "REAL",
    "text": "TEXT",
    "timestamptz": "TEXT",
    "uuid": "TEXT",
}


def physical_table_name(schema_name: str, table_name: str) -> str:
    return f"{schema_name}__{table_name}"


def apply_plugin_bundle_migrations(db: PlatformDatabase, bundle_dir: Path) -> list[str]:
    """Reads data-only plugin bundles (never imports plugins/) and applies metric tables + reporting view."""
    applied_namespaces: list[str] = []
    if not bundle_dir.exists():
        return applied_namespaces

    health_tables: list[tuple[str, str]] = []

    for plugin_dir in sorted(bundle_dir.iterdir()):
        if not plugin_dir.is_dir():
            continue
        versions = sorted([v for v in plugin_dir.iterdir() if v.is_dir()])
        if not versions:
            continue
        latest = versions[-1]
        schema_file = latest / "schema_manifest.json"
        if not schema_file.exists():
            continue

        schema_data: dict[str, Any] = json.loads(schema_file.read_text(encoding="utf-8"))
        manifest = SchemaManifest.from_dict(schema_data)
        validate_schema_manifest(manifest)

        # Verify forward-only SQL migration checksums from bundle
        checksum_file = latest / "migrations_checksums.json"
        expected_checksums: dict[str, str] = (
            json.loads(checksum_file.read_text(encoding="utf-8"))
            if checksum_file.exists()
            else {}
        )
        mig_dir = latest / "migrations"
        if mig_dir.exists():
            for sql_file in sorted(mig_dir.glob("*.sql")):
                digest = hashlib.sha256(sql_file.read_bytes()).hexdigest()
                if sql_file.name in expected_checksums and expected_checksums[sql_file.name] != digest:
                    raise RuntimeError(
                        f"Checksum mismatch for migration {sql_file.name} in {manifest.plugin_id}."
                    )

        with db.transaction() as conn:
            for tname, table in manifest.tables.items():
                phys = physical_table_name(manifest.schema, tname)
                col_defs = [
                    "server_id TEXT NOT NULL",
                    "polling_run_id TEXT NOT NULL",
                    "collected_at TEXT NOT NULL",
                ]
                for cname, col in table.columns.items():
                    sql_type = _SQLITE_TYPE_MAP[col.type]
                    null_clause = "" if col.nullable else " NOT NULL"
                    col_defs.append(f"{cname} {sql_type}{null_clause}")

                pk_cols = ["polling_run_id", "collected_at", *table.natural_key]
                pk_clause = f"PRIMARY KEY ({', '.join(pk_cols)})"
                conn.execute(
                    f"CREATE TABLE IF NOT EXISTS {phys} ({', '.join(col_defs)}, {pk_clause});"
                )
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{phys}_server_time "
                    f"ON {phys} (server_id, collected_at DESC);"
                )
                if tname == "instance_health":
                    health_tables.append((manifest.db_type, phys))

                # Seed initial partition catalog metadata for visibility
                now_str = utc_now_iso()
                day_str = now_str[:10]
                part_name = f"{tname}_{day_str.replace('-', '')}"
                conn.execute(
                    """
                    INSERT OR IGNORE INTO platform_partition_catalog (
                        partition_id, schema_name, table_name, partition_name,
                        range_start, range_end, retention_days, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_uuid(),
                        manifest.schema,
                        tname,
                        part_name,
                        f"{day_str}T00:00:00Z",
                        f"{day_str}T23:59:59Z",
                        table.retention_days,
                        now_str,
                    ),
                )

            conn.execute(
                """
                INSERT INTO platform_plugin_schema_versions (
                    namespace, plugin_id, schema_version, checksums_json, applied_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(namespace) DO UPDATE SET
                    plugin_id = excluded.plugin_id,
                    schema_version = excluded.schema_version,
                    checksums_json = excluded.checksums_json,
                    applied_at = excluded.applied_at
                """,
                (
                    manifest.schema,
                    manifest.plugin_id,
                    manifest.schema_version,
                    json.dumps(expected_checksums),
                    utc_now_iso(),
                ),
            )
        applied_namespaces.append(manifest.schema)
        log.info(
            "plugin_schema_migrated",
            namespace=manifest.schema,
            plugin_id=manifest.plugin_id,
            schema_version=manifest.schema_version,
        )

    # Create/refresh reporting.instance_health cross-engine union view (Section 3.2 & 11.2)
    if health_tables:
        with db.transaction() as conn:
            conn.execute("DROP VIEW IF EXISTS reporting_instance_health;")
            unions = [
                f"SELECT '{db_type}' AS db_type, server_id, polling_run_id, collected_at, is_available, response_time_ms FROM {phys}"
                for db_type, phys in health_tables
            ]
            conn.execute(
                f"CREATE VIEW reporting_instance_health AS {' UNION ALL '.join(unions)};"
            )

    return applied_namespaces
