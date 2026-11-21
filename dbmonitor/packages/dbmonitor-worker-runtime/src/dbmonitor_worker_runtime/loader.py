from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from dbmonitor_common.identifiers import validate_db_type
from dbmonitor_common.logging import get_logger
from dbmonitor_sdk.contracts.manifest import PluginManifest

log = get_logger("worker-runtime.loader")

DEFAULT_PROVIDER_ENTRYPOINTS: dict[str, str] = {
    "dbmonitor-provider-cmdb": "dbmonitor_provider_cmdb.plugin:plugin",
    "dbmonitor-provider-cloud": "dbmonitor_provider_cloud.plugin:plugin",
}

DEFAULT_POLLER_ENTRYPOINTS: dict[str, str] = {
    "postgresql": "dbmonitor_poller_postgresql.plugin:plugin",
    "oracle": "dbmonitor_poller_oracle.plugin:plugin",
    "mssql": "dbmonitor_poller_mssql.plugin:plugin",
}


@dataclass
class LoadedPoller:
    plugin: Any
    manifest: PluginManifest
    queue: str


def _load_entrypoint(spec: str) -> Any:
    module_path, attr = spec.split(":", 1)
    mod = importlib.import_module(module_path)
    return getattr(mod, attr)


def load_poller_worker_plugin(
    db_type: str,
    pool: str,
    entrypoint: str | None = None,
) -> LoadedPoller:
    validate_db_type(db_type)
    ep = entrypoint or DEFAULT_POLLER_ENTRYPOINTS.get(db_type)
    if not ep:
        raise RuntimeError(f"No poller entry point configured for db_type '{db_type}'.")

    plugin = _load_entrypoint(ep)
    manifest: PluginManifest = plugin.manifest
    if manifest.kind != "poller":
        raise RuntimeError(f"Plugin '{manifest.plugin_id}' kind is '{manifest.kind}', expected 'poller'.")
    if manifest.db_type != db_type or getattr(plugin, "db_type", None) != db_type:
        raise RuntimeError(
            f"Startup validation failed: worker configured for db_type '{db_type}', "
            f"but plugin declares '{manifest.db_type}'."
        )
    expected_queue = f"poll.{db_type}.{pool}"
    log.info(
        "poller_plugin_loaded",
        plugin_id=manifest.plugin_id,
        plugin_version=manifest.version,
        db_type=db_type,
        pool=pool,
        queue=expected_queue,
    )
    return LoadedPoller(plugin=plugin, manifest=manifest, queue=expected_queue)


def load_discovery_plugins(
    entrypoints: dict[str, str] | None = None,
) -> dict[str, Any]:
    eps = entrypoints or DEFAULT_PROVIDER_ENTRYPOINTS
    loaded: dict[str, Any] = {}
    for plugin_id, ep in eps.items():
        try:
            plugin = _load_entrypoint(ep)
            manifest: PluginManifest = plugin.manifest
            if manifest.kind != "provider":
                raise ValueError(f"Expected kind 'provider', got '{manifest.kind}'.")
            loaded[manifest.plugin_id] = plugin
            log.info(
                "provider_plugin_loaded",
                plugin_id=manifest.plugin_id,
                plugin_version=manifest.version,
            )
        except Exception as exc:
            # Section 6: Report invalid plugin without preventing unrelated plugins from loading.
            log.error("provider_plugin_load_failed", plugin_id=plugin_id, error=str(exc))
    return loaded
