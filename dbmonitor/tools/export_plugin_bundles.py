#!/usr/bin/env python3
"""Exports data-only plugin bundles to dbmonitor/build/plugin-bundles/<plugin_id>/<version>/."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in [
    ROOT / "packages" / "dbmonitor-sdk" / "src",
    ROOT / "plugins" / "providers" / "cmdb" / "src",
    ROOT / "plugins" / "providers" / "cloud" / "src",
    ROOT / "plugins" / "pollers" / "postgresql" / "src",
    ROOT / "plugins" / "pollers" / "oracle" / "src",
    ROOT / "plugins" / "pollers" / "mssql" / "src",
]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dbmonitor_poller_mssql.manifest import MANIFEST as MSSQL_MANIFEST
from dbmonitor_poller_oracle.manifest import MANIFEST as ORACLE_MANIFEST
from dbmonitor_poller_postgresql.manifest import MANIFEST as PG_MANIFEST
from dbmonitor_provider_cloud.manifest import MANIFEST as CLOUD_MANIFEST
from dbmonitor_provider_cmdb.manifest import MANIFEST as CMDB_MANIFEST
from dbmonitor_sdk.bundle.export import export_plugin_bundle
from dbmonitor_sdk.contracts.schema import SchemaManifest


def export_all(output_root: Path | None = None) -> list[Path]:
    out = output_root or (ROOT / "build" / "plugin-bundles")
    out.mkdir(parents=True, exist_ok=True)
    exported: list[Path] = []

    for provider_manifest in (CMDB_MANIFEST, CLOUD_MANIFEST):
        exported.append(export_plugin_bundle(provider_manifest, out))

    poller_specs = [
        (
            PG_MANIFEST,
            ROOT / "plugins" / "pollers" / "postgresql" / "src" / "dbmonitor_poller_postgresql" / "schema",
        ),
        (
            ORACLE_MANIFEST,
            ROOT / "plugins" / "pollers" / "oracle" / "src" / "dbmonitor_poller_oracle" / "schema",
        ),
        (
            MSSQL_MANIFEST,
            ROOT / "plugins" / "pollers" / "mssql" / "src" / "dbmonitor_poller_mssql" / "schema",
        ),
    ]

    for manifest, schema_dir in poller_specs:
        schema_data = json.loads((schema_dir / "manifest.json").read_text(encoding="utf-8"))
        schema_manifest = SchemaManifest.from_dict(schema_data)
        exported.append(
            export_plugin_bundle(
                manifest=manifest,
                output_root=out,
                schema_manifest=schema_manifest,
                migrations_dir=schema_dir / "migrations",
            )
        )
    return exported


if __name__ == "__main__":
    paths = export_all()
    for path in paths:
        print(f"Exported bundle: {path.relative_to(ROOT)}")
