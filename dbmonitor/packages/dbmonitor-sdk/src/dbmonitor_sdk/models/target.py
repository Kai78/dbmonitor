from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DatabaseTarget:
    server_id: str
    hostname: str
    address: str
    port: int
    db_type: str
    environment: str
    region: str
    network_zone: str
    secret_ref: str
    config_version: int
    tags: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "hostname": self.hostname,
            "address": self.address,
            "port": self.port,
            "db_type": self.db_type,
            "environment": self.environment,
            "region": self.region,
            "network_zone": self.network_zone,
            "secret_ref": self.secret_ref,
            "config_version": int(self.config_version),
            "tags": dict(self.tags),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatabaseTarget":
        return cls(
            server_id=data["server_id"],
            hostname=data["hostname"],
            address=data["address"],
            port=int(data["port"]),
            db_type=data["db_type"],
            environment=data["environment"],
            region=data["region"],
            network_zone=data.get("network_zone", "default"),
            secret_ref=data["secret_ref"],
            config_version=int(data["config_version"]),
            tags=dict(data.get("tags", {})),
            metadata=dict(data.get("metadata", {})),
        )
