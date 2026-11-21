from dbmonitor_sdk.contracts.manifest import CollectorGroupSpec, PluginManifest

MANIFEST = PluginManifest(
    plugin_id="dbmonitor-poller-postgresql",
    kind="poller",
    version="1.0.0",
    sdk_range=">=1.0,<2.0",
    db_type="postgresql",
    schema_version="0003",
    collector_groups={
        "health": CollectorGroupSpec(min_interval_seconds=30, default_timeout_seconds=10),
        "sessions": CollectorGroupSpec(min_interval_seconds=30, default_timeout_seconds=10),
        "replication": CollectorGroupSpec(min_interval_seconds=30, default_timeout_seconds=10),
        "performance": CollectorGroupSpec(min_interval_seconds=300, default_timeout_seconds=60),
        "capacity": CollectorGroupSpec(min_interval_seconds=600, default_timeout_seconds=90),
    },
    default_pools=("high_frequency", "low_frequency"),
    description="PostgreSQL database poller plugin (health, sessions, replication, performance, capacity)",
)
