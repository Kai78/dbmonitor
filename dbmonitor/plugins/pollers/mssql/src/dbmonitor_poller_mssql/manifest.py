from dbmonitor_sdk.contracts.manifest import CollectorGroupSpec, PluginManifest

MANIFEST = PluginManifest(
    plugin_id="dbmonitor-poller-mssql",
    kind="poller",
    version="1.0.0",
    sdk_range=">=1.0,<2.0",
    db_type="mssql",
    schema_version="0002",
    collector_groups={
        "health": CollectorGroupSpec(min_interval_seconds=30, default_timeout_seconds=12),
        "sessions": CollectorGroupSpec(min_interval_seconds=30, default_timeout_seconds=12),
        "performance": CollectorGroupSpec(min_interval_seconds=300, default_timeout_seconds=60),
        "capacity": CollectorGroupSpec(min_interval_seconds=600, default_timeout_seconds=120),
    },
    default_pools=("high_frequency", "low_frequency"),
    description="Microsoft SQL Server poller plugin (health, sessions, performance, capacity)",
)
