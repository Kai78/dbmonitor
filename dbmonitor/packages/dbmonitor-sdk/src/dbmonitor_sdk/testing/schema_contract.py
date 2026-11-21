from __future__ import annotations

from dbmonitor_sdk.contracts.schema import SchemaManifest
from dbmonitor_sdk.validation.schema_contract import (
    build_table_json_schema,
    validate_schema_manifest,
)


def verify_schema_contract(schema_manifest: SchemaManifest) -> list[str]:
    checks: list[str] = []
    validate_schema_manifest(schema_manifest)
    checks.append(
        f"schema '{schema_manifest.schema}' v{schema_manifest.schema_version} passed manifest validation"
    )
    for tname in schema_manifest.tables:
        js = build_table_json_schema(schema_manifest, tname)
        assert js["additionalProperties"] is False
    checks.append(f"generated strict JSON Schemas for {len(schema_manifest.tables)} tables")
    return checks
