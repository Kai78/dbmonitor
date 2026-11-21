from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ColumnSchema:
    name: str
    type: Literal["boolean", "integer", "bigint", "double", "text", "timestamptz", "uuid"]
    nullable: bool = True
    unit: str | None = None
    description: str = ""


@dataclass(frozen=True)
class TableSchema:
    name: str
    partition_column: str
    partition_interval: Literal["day", "week", "month"]
    retention_days: int
    columns: dict[str, ColumnSchema]
    required: bool = False
    natural_key: tuple[str, ...] = ()


@dataclass(frozen=True)
class SchemaManifest:
    plugin_id: str
    db_type: str
    schema: str
    schema_version: str
    tables: dict[str, TableSchema] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SchemaManifest":
        tables: dict[str, TableSchema] = {}
        for tname, tdata in data.get("tables", {}).items():
            cols: dict[str, ColumnSchema] = {}
            for cname, cdata in tdata.get("columns", {}).items():
                cols[cname] = ColumnSchema(
                    name=cname,
                    type=cdata["type"],
                    nullable=bool(cdata.get("nullable", True)),
                    unit=cdata.get("unit"),
                    description=cdata.get("description", ""),
                )
            part = tdata.get("partition", {})
            tables[tname] = TableSchema(
                name=tname,
                partition_column=part.get("column", "collected_at"),
                partition_interval=part.get("interval", "day"),
                retention_days=int(tdata.get("retention_days", 14)),
                columns=cols,
                required=bool(tdata.get("required", False)),
                natural_key=tuple(tdata.get("natural_key", ())),
            )
        return cls(
            plugin_id=data["plugin_id"],
            db_type=data["db_type"],
            schema=data["schema"],
            schema_version=str(data["schema_version"]),
            tables=tables,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "db_type": self.db_type,
            "schema": self.schema,
            "schema_version": self.schema_version,
            "tables": {
                tname: {
                    "required": table.required,
                    "partition": {
                        "column": table.partition_column,
                        "interval": table.partition_interval,
                    },
                    "retention_days": table.retention_days,
                    "natural_key": list(table.natural_key),
                    "columns": {
                        cname: {
                            "type": col.type,
                            "nullable": col.nullable,
                            **({"unit": col.unit} if col.unit else {}),
                            **({"description": col.description} if col.description else {}),
                        }
                        for cname, col in table.columns.items()
                    },
                }
                for tname, table in self.tables.items()
            },
        }
