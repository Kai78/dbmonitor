from __future__ import annotations

from typing import Iterable

from dbmonitor_provider_cloud.manifest import MANIFEST
from dbmonitor_sdk.models.server import DiscoveredServer, DiscoveryContext

_CLOUD_CATALOG: list[dict] = [
    {
        "provider_resource_id": "arn:aws:rds:eu-west-1:111122223333:db:analytics-pg-01",
        "hostname": "analytics-pg-01.rds.eu-west-1.internal",
        "address": "10.30.1.40",
        "port": 5432,
        "db_type": "postgresql",
        "environment": "production",
        "region": "eu-west-1",
        "network_zone": "default",
        "tags": {"tier": "high", "team": "analytics", "cloud": "aws"},
        "ownership": "data-eng",
        "secret_ref": "secret://aws-sm/prod/rds/analytics-pg-01",
        "metadata": {"engine_version": "15.8", "instance_class": "db.r6g.2xlarge"},
    },
    {
        "provider_resource_id": "azure:sql:prod-westeurope:orders-dw",
        "hostname": "orders-dw.database.windows.net",
        "address": "10.30.4.18",
        "port": 1433,
        "db_type": "mssql",
        "environment": "production",
        "region": "westeurope",
        "network_zone": "default",
        "tags": {"tier": "high", "team": "data-warehouse", "cloud": "azure"},
        "ownership": "bi-platform",
        "secret_ref": "secret://azure-kv/prod/mssql/orders-dw",
        "metadata": {"engine_version": "AzureSQL-v12", "tier": "BusinessCritical"},
    },
    {
        "provider_resource_id": "arn:aws:rds:eu-west-1:111122223333:db:staging-pg-01",
        "hostname": "staging-pg-01.rds.eu-west-1.internal",
        "address": "10.31.1.12",
        "port": 5432,
        "db_type": "postgresql",
        "environment": "staging",
        "region": "eu-west-1",
        "network_zone": "default",
        "tags": {"tier": "standard", "team": "checkout", "cloud": "aws"},
        "ownership": "checkout-dba",
        "secret_ref": "secret://aws-sm/stg/rds/staging-pg-01",
        "metadata": {"engine_version": "16.2", "instance_class": "db.t4g.medium"},
    },
]


class CloudDiscoveryPlugin:
    plugin_id = MANIFEST.plugin_id
    manifest = MANIFEST

    def discover(self, context: DiscoveryContext) -> Iterable[list[DiscoveredServer]]:
        account = context.config.get("account", "prod")
        items = list(_CLOUD_CATALOG)
        if account == "staging":
            items = [i for i in items if i["environment"] == "staging"]
        elif account == "prod":
            items = [i for i in items if i["environment"] == "production"]

        extra = context.config.get("extra_servers", [])
        items.extend(extra)

        yield [
            DiscoveredServer(
                provider="cloud",
                provider_resource_id=item["provider_resource_id"],
                hostname=item["hostname"],
                address=item["address"],
                port=int(item["port"]),
                db_type=item["db_type"],
                environment=item.get("environment", "production"),
                region=item.get("region", "eu-west-1"),
                network_zone=item.get("network_zone", "default"),
                tags=dict(item.get("tags", {})),
                ownership=item.get("ownership", "platform-dba"),
                secret_ref=item["secret_ref"],
                metadata=dict(item.get("metadata", {})),
            )
            for item in items
        ]


plugin = CloudDiscoveryPlugin()
