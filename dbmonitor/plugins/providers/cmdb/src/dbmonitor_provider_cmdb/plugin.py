from __future__ import annotations

from typing import Iterable

from dbmonitor_provider_cmdb.manifest import MANIFEST
from dbmonitor_sdk.models.server import DiscoveredServer, DiscoveryContext

_CMDB_CATALOG: list[dict] = [
    {
        "provider_resource_id": "cmdb-pg-prod-01",
        "hostname": "pg-orders-01.prod.internal",
        "address": "10.10.1.11",
        "port": 5432,
        "db_type": "postgresql",
        "environment": "production",
        "region": "eu-west-1",
        "network_zone": "default",
        "tags": {"tier": "critical", "team": "checkout", "compliance": "pci"},
        "ownership": "checkout-dba",
        "secret_ref": "secret://vault/prod/postgresql/orders-01",
        "metadata": {"engine_version": "16.4", "cluster": "orders-primary"},
    },
    {
        "provider_resource_id": "cmdb-pg-prod-02",
        "hostname": "pg-ledger-01.prod.internal",
        "address": "10.10.1.12",
        "port": 5432,
        "db_type": "postgresql",
        "environment": "production",
        "region": "eu-west-1",
        "network_zone": "default",
        "tags": {"tier": "critical", "team": "billing"},
        "ownership": "billing-dba",
        "secret_ref": "secret://vault/prod/postgresql/ledger-01",
        "metadata": {"engine_version": "16.4", "cluster": "ledger-primary"},
    },
    {
        "provider_resource_id": "cmdb-ora-prod-01",
        "hostname": "ora-erp-01.prod.internal",
        "address": "10.10.2.21",
        "port": 1521,
        "db_type": "oracle",
        "environment": "production",
        "region": "eu-central-1",
        "network_zone": "default",
        "tags": {"tier": "critical", "team": "erp"},
        "ownership": "core-oracle-dba",
        "secret_ref": "secret://vault/prod/oracle/erp-01",
        "metadata": {"engine_version": "19c", "service_name": "ERPPROD"},
    },
    {
        "provider_resource_id": "cmdb-ora-stg-01",
        "hostname": "ora-erp-stg.stg.internal",
        "address": "10.20.2.21",
        "port": 1521,
        "db_type": "oracle",
        "environment": "staging",
        "region": "eu-central-1",
        "network_zone": "default",
        "tags": {"tier": "standard", "team": "erp"},
        "ownership": "core-oracle-dba",
        "secret_ref": "secret://vault/stg/oracle/erp-stg",
        "metadata": {"engine_version": "19c", "service_name": "ERPSTG"},
    },
    {
        "provider_resource_id": "cmdb-mssql-prod-01",
        "hostname": "sql-hr-01.prod.internal",
        "address": "10.10.3.31",
        "port": 1433,
        "db_type": "mssql",
        "environment": "production",
        "region": "eu-west-1",
        "network_zone": "default",
        "tags": {"tier": "high", "team": "people-ops"},
        "ownership": "windows-data-ops",
        "secret_ref": "secret://vault/prod/mssql/hr-01",
        "metadata": {"engine_version": "2022", "instance": "MSSQLSERVER"},
    },
]


class CmdbDiscoveryPlugin:
    plugin_id = MANIFEST.plugin_id
    manifest = MANIFEST

    def discover(self, context: DiscoveryContext) -> Iterable[list[DiscoveredServer]]:
        env_filter = context.config.get("environment")
        extra_servers = context.config.get("extra_servers", [])
        records = list(_CMDB_CATALOG) + list(extra_servers)

        page: list[DiscoveredServer] = []
        for item in records:
            if env_filter and item.get("environment") != env_filter:
                continue
            page.append(
                DiscoveredServer(
                    provider="cmdb",
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
            )
            if len(page) >= 3:
                yield page
                page = []
        if page or not records:
            yield page


plugin = CmdbDiscoveryPlugin()
