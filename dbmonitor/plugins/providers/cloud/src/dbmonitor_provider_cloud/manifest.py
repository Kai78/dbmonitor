from dbmonitor_sdk.contracts.manifest import PluginManifest

MANIFEST = PluginManifest(
    plugin_id="dbmonitor-provider-cloud",
    kind="provider",
    version="1.0.0",
    sdk_range=">=1.0,<2.0",
    provider_name="cloud",
    description="Multi-cloud managed database inventory provider (RDS / Azure SQL / Cloud SQL)",
)
