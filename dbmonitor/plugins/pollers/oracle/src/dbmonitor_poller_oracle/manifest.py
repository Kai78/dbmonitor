from dbmonitor_sdk.contracts.manifest import CollectorGroupSpec, PluginManifest

MANIFEST = PluginManifest(
    plugin_id="dbmonitor-poller-oracle",
    kind="poller",
    version="1.0.0",
    sdk_range=">=1.0,<2.0",
    db_type="oracle",
    schema_version="0002",
    collector_groups={
        "health": CollectorGroupSpec(min_interval_seconds=30, default_timeout_seconds=15),
        "sessions": CollectorGroupSpec(min_interval_seconds=30, default_timeout_seconds=15),
        "performance": CollectorGroupSpec(min_interval_seconds=300, default_timeout_seconds=60),
        "capacity": CollectorGroupSpec(min_interval_seconds=600, default_timeout_seconds=120),
    },
    default_pools=("high_frequency", "low_frequency"),
    description="Oracle Database poller plugin (health, sessions, performance, capacity)",
)
