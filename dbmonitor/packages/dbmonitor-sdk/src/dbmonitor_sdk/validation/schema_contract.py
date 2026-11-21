from __future__ import annotations

import re
from typing import Any

from dbmonitor_sdk.contracts.schema import ColumnSchema, SchemaManifest
from dbmonitor_sdk.errors import SchemaValidationError

_VALID_DB_TYPE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_UNIT_SUFFIXES = {
    "ms": "_ms",
    "bytes": "_bytes",
    "percent": "_percent",
    "seconds": "_seconds",
}


def validate_schema_manifest(manifest: SchemaManifest) -> None:
    if not _VALID_DB_TYPE.match(manifest.db_type):
        raise SchemaValidationError(f"Invalid db_type '{manifest.db_type}'.")

    expected_schema = f"metrics_{manifest.db_type}"
    if manifest.schema != expected_schema:
        raise SchemaValidationError(
            f"Schema name must be '{expected_schema}', got '{manifest.schema}'."
        )

    if "instance_health" not in manifest.tables:
        raise SchemaValidationError(
            f"Plugin '{manifest.plugin_id}' must declare required 'instance_health' table."
        )

    health = manifest.tables["instance_health"]
    for req_col, req_type in (("is_available", "boolean"), ("response_time_ms", "integer")):
        col = health.columns.get(req_col)
        if col is None or col.type != req_type:
            raise SchemaValidationError(
                f"'instance_health' must define '{req_col}' with type '{req_type}'."
            )

    for tname, table in manifest.tables.items():
        if table.partition_column != "collected_at":
            raise SchemaValidationError(
                f"Table '{tname}' must partition on 'collected_at', got '{table.partition_column}'."
            )
        if table.retention_days <= 0:
            raise SchemaValidationError(
                f"Table '{tname}' retention_days must be > 0."
            )
        for cname, col in table.columns.items():
            if col.unit and col.unit in _UNIT_SUFFIXES:
                suffix = _UNIT_SUFFIXES[col.unit]
                if not cname.endswith(suffix):
                    raise SchemaValidationError(
                        f"Column '{tname}.{cname}' declares unit '{col.unit}' "
                        f"and must end with '{suffix}'."
                    )


def build_table_json_schema(schema_manifest: SchemaManifest, table_name: str) -> dict[str, Any]:
    table = schema_manifest.tables[table_name]
    properties: dict[str, Any] = {}
    required: list[str] = []

    type_map = {
        "boolean": "boolean",
        "integer": "integer",
        "bigint": "integer",
        "double": "number",
        "text": "string",
        "timestamptz": "string",
        "uuid": "string",
    }

    for cname, col in table.columns.items():
        json_type = type_map[col.type]
        if col.nullable:
            properties[cname] = {"type": [json_type, "null"]}
        else:
            properties[cname] = {"type": json_type}
            required.append(cname)

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"{schema_manifest.schema}.{table_name}",
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
        "x-dbmonitor": {
            "schema": schema_manifest.schema,
            "table": table_name,
            "partition": {
                "column": table.partition_column,
                "interval": table.partition_interval,
            },
            "retention_days": table.retention_days,
            "natural_key": list(table.natural_key),
        },
    }


def _check_value_type(value: Any, expected: str) -> bool:
    if expected == "boolean":
        return isinstance(value, bool)
    if expected in ("integer", "bigint"):
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "double":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected in ("text", "timestamptz", "uuid"):
        return isinstance(value, str)
    return False


def validate_rows_against_json_schema(
    table_name: str,
    rows: list[dict[str, Any]],
    json_schema: dict[str, Any],
    column_types: dict[str, ColumnSchema] | None = None,
) -> None:
    allowed_cols = set(json_schema["properties"].keys())
    required_cols = set(json_schema.get("required", []))

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            raise SchemaValidationError(f"{table_name}[{idx}] must be an object.")
        unknown = set(row.keys()) - allowed_cols
        if unknown:
            raise SchemaValidationError(
                f"{table_name}[{idx}] contains undeclared columns: {sorted(unknown)}"
            )
        missing = required_cols - set(row.keys())
        if missing:
            raise SchemaValidationError(
                f"{table_name}[{idx}] missing required columns: {sorted(missing)}"
            )
        for col_name, val in row.items():
            prop_type = json_schema["properties"][col_name]["type"]
            if val is None:
                if isinstance(prop_type, list) and "null" in prop_type:
                    continue
                raise SchemaValidationError(
                    f"{table_name}[{idx}].{col_name} cannot be null."
                )
            expected = (
                column_types[col_name].type
                if column_types and col_name in column_types
                else (prop_type[0] if isinstance(prop_type, list) else prop_type)
            )
            if expected == "number":
                expected = "double"
            elif expected == "string":
                expected = "text"
            if not _check_value_type(val, expected):
                raise SchemaValidationError(
                    f"{table_name}[{idx}].{col_name} expected {expected}, got {type(val).__name__}."
                )
