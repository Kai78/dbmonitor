from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from dbmonitor_sdk.contracts.manifest import PluginManifest
from dbmonitor_sdk.contracts.schema import SchemaManifest
from dbmonitor_sdk.validation.schema_contract import (
    build_table_json_schema,
    validate_schema_manifest,
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_plugin_bundle(
    manifest: PluginManifest,
    output_root: Path,
    schema_manifest: SchemaManifest | None = None,
    migrations_dir: Path | None = None,
) -> Path:
    """Exports a data-only plugin bundle (no Python plugin code) to output_root/<plugin_id>/<version>/."""
    bundle_dir = output_root / manifest.plugin_id / manifest.version
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    (bundle_dir / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )

    if schema_manifest is not None:
        validate_schema_manifest(schema_manifest)
        (bundle_dir / "schema_manifest.json").write_text(
            json.dumps(schema_manifest.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

        json_schemas_dir = bundle_dir / "json_schemas"
        json_schemas_dir.mkdir(exist_ok=True)
        for table_name in schema_manifest.tables:
            schema_doc = build_table_json_schema(schema_manifest, table_name)
            (json_schemas_dir / f"{table_name}.schema.json").write_text(
                json.dumps(schema_doc, indent=2) + "\n",
                encoding="utf-8",
            )

        mig_out = bundle_dir / "migrations"
        mig_out.mkdir(exist_ok=True)
        checksums: dict[str, Any] = {}
        if migrations_dir and migrations_dir.exists():
            for sql_file in sorted(migrations_dir.glob("*.sql")):
                content = sql_file.read_text(encoding="utf-8")
                if "platform." in content.lower() and ("alter table platform." in content.lower() or "drop table platform." in content.lower()):
                    raise ValueError(
                        f"Migration '{sql_file.name}' attempts DDL on platform schema, which is forbidden."
                    )
                dest = mig_out / sql_file.name
                dest.write_text(content, encoding="utf-8")
                checksums[sql_file.name] = sha256_file(dest)
        (bundle_dir / "migrations_checksums.json").write_text(
            json.dumps(checksums, indent=2) + "\n",
            encoding="utf-8",
        )

    return bundle_dir
