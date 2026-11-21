from __future__ import annotations

from dbmonitor_sdk.contracts.discovery import DiscoveryPlugin
from dbmonitor_sdk.contracts.manifest import PluginManifest
from dbmonitor_sdk.models.server import DiscoveredServer, DiscoveryContext


def verify_provider_contract(plugin: DiscoveryPlugin, manifest: PluginManifest) -> list[str]:
    checks: list[str] = []
    assert manifest.kind == "provider", "Provider manifest kind must be 'provider'."
    assert plugin.plugin_id == manifest.plugin_id, "plugin_id mismatch between plugin and manifest."
    checks.append(f"manifest.kind == provider ({manifest.plugin_id})")

    ctx = DiscoveryContext(
        run_id="contract-test-run",
        provider_instance_id="contract-test-instance",
        provider_name=manifest.provider_name or manifest.plugin_id,
        config={"environment": "staging"},
        dry_run=True,
    )
    pages = list(plugin.discover(ctx))
    assert isinstance(pages, list) and len(pages) >= 1, "discover() must yield at least one page."
    for page in pages:
        assert isinstance(page, list), "Each discovered page must be a list."
        for item in page:
            assert isinstance(item, DiscoveredServer), "Discovered items must be DiscoveredServer instances."
            assert item.provider_resource_id, "provider_resource_id is required."
            assert item.hostname and item.address and item.port > 0, "Network coordinates required."
            assert not ("password" in item.secret_ref.lower() and "secret://" not in item.secret_ref.lower()), "Must use secret reference, never raw credentials."
    checks.append(f"discover() yielded {sum(len(p) for p in pages)} normalized DiscoveredServer records")
    return checks
