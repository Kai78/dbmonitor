from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dbmonitor_common.identifiers import utc_now_iso
from dbmonitor_common.logging import get_logger
from dbmonitor_platform_db.database import PlatformDatabase

log = get_logger("plugin-registry")


def sync_bundles_to_registry(db: PlatformDatabase, bundle_dir: Path) -> list[dict[str, Any]]:
    """Loads data-only bundles from build/plugin-bundles/ into platform_plugin_registry."""
    registered: list[dict[str, Any]] = []
    if not bundle_dir.exists():
        return registered

    with db.transaction() as conn:
        for plugin_dir in sorted(bundle_dir.iterdir()):
            if not plugin_dir.is_dir():
                continue
            versions = sorted([v for v in plugin_dir.iterdir() if v.is_dir()])
            if not versions:
                continue
            latest = versions[-1]
            manifest_path = latest / "manifest.json"
            if not manifest_path.exists():
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            plugin_id = manifest["plugin_id"]
            kind = manifest["kind"]
            version = manifest["version"]
            db_type = manifest.get("db_type")
            provider_name = manifest.get("provider_name")
            schema_version = manifest.get("schema_version")
            groups_json = json.dumps(manifest.get("collector_groups", {}))
            default_pools = manifest.get("default_pools", [])

            existing = conn.execute(
                "SELECT enabled, enabled_pools_json FROM platform_plugin_registry WHERE plugin_id = ?",
                (plugin_id,),
            ).fetchone()
            enabled = existing["enabled"] if existing else 1
            enabled_pools_json = (
                existing["enabled_pools_json"]
                if existing
                else json.dumps(default_pools)
            )

            conn.execute(
                """
                INSERT INTO platform_plugin_registry (
                    plugin_id, kind, version, db_type, provider_name,
                    schema_version, collector_groups_json, enabled_pools_json,
                    enabled, drift_detected, bundle_path, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(plugin_id) DO UPDATE SET
                    kind = excluded.kind,
                    version = excluded.version,
                    db_type = excluded.db_type,
                    provider_name = excluded.provider_name,
                    schema_version = excluded.schema_version,
                    collector_groups_json = excluded.collector_groups_json,
                    bundle_path = excluded.bundle_path,
                    updated_at = excluded.updated_at
                """,
                (
                    plugin_id,
                    kind,
                    version,
                    db_type,
                    provider_name,
                    schema_version,
                    groups_json,
                    enabled_pools_json,
                    enabled,
                    str(latest),
                    utc_now_iso(),
                ),
            )
            registered.append(manifest)
            log.info(
                "bundle_registered",
                plugin_id=plugin_id,
                kind=kind,
                version=version,
                db_type=db_type,
            )
    return registered
