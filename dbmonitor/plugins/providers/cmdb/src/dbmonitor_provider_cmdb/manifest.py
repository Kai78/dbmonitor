from dbmonitor_sdk.contracts.manifest import PluginManifest

MANIFEST = PluginManifest(
    plugin_id="dbmonitor-provider-cmdb",
    kind="provider",
    version="1.0.0",
    sdk_range=">=1.0,<2.0",
    provider_name="cmdb",
    description="Enterprise CMDB database asset inventory discovery provider",
)
