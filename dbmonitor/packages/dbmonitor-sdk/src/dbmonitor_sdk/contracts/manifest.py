from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class CollectorGroupSpec:
    min_interval_seconds: int
    default_timeout_seconds: int

    def to_dict(self) -> dict[str, int]:
        return {
            "min_interval_seconds": self.min_interval_seconds,
            "default_timeout_seconds": self.default_timeout_seconds,
        }


@dataclass(frozen=True)
class PluginManifest:
    plugin_id: str
    kind: Literal["provider", "poller"]
    version: str
    sdk_range: str
    db_type: str | None = None
    provider_name: str | None = None
    schema_version: str | None = None
    collector_groups: dict[str, CollectorGroupSpec] = field(default_factory=dict)
    default_pools: tuple[str, ...] = ("high_frequency", "low_frequency")
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "kind": self.kind,
            "version": self.version,
            "sdk_range": self.sdk_range,
            "db_type": self.db_type,
            "provider_name": self.provider_name,
            "schema_version": self.schema_version,
            "collector_groups": {
                name: spec.to_dict() for name, spec in self.collector_groups.items()
            },
            "default_pools": list(self.default_pools),
            "description": self.description,
        }
