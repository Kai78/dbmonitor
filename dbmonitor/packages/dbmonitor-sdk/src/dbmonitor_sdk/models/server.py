from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DiscoveredServer:
    provider: str
    provider_resource_id: str
    hostname: str
    address: str
    port: int
    db_type: str
    environment: str = "production"
    region: str = "eu-west-1"
    network_zone: str = "default"
    tags: dict[str, str] = field(default_factory=dict)
    ownership: str = "platform-dba"
    secret_ref: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "provider_resource_id": self.provider_resource_id,
            "hostname": self.hostname,
            "address": self.address,
            "port": self.port,
            "db_type": self.db_type,
            "environment": self.environment,
            "region": self.region,
            "network_zone": self.network_zone,
            "tags": dict(self.tags),
            "ownership": self.ownership,
            "secret_ref": self.secret_ref,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DiscoveredServer":
        return cls(
            provider=data["provider"],
            provider_resource_id=data["provider_resource_id"],
            hostname=data["hostname"],
            address=data["address"],
            port=int(data["port"]),
            db_type=data["db_type"],
            environment=data.get("environment", "production"),
            region=data.get("region", "eu-west-1"),
            network_zone=data.get("network_zone", "default"),
            tags=dict(data.get("tags", {})),
            ownership=data.get("ownership", "platform-dba"),
            secret_ref=data.get("secret_ref", ""),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class DiscoveryContext:
    run_id: str
    provider_instance_id: str
    provider_name: str
    config: dict[str, Any]
    dry_run: bool = False
