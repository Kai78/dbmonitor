from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LoadedBundle:
    plugin_id: str
    version: str
    db_type: str | None
    schema_name: str | None
    schema_version: str | None
    json_schemas: dict[str, dict[str, Any]]
    raw_manifest: dict[str, Any]
    raw_schema_manifest: dict[str, Any] | None


class BundleStore:
    """Data-only bundle loader for results-processor. Never imports plugin code."""

    def __init__(self, bundle_dir: Path) -> None:
        self.bundle_dir = bundle_dir
        self._by_plugin: dict[str, LoadedBundle] = {}
        self.reload()

    def reload(self) -> None:
        loaded: dict[str, LoadedBundle] = {}
        if not self.bundle_dir.exists():
            self._by_plugin = loaded
            return

        for pdir in sorted(self.bundle_dir.iterdir()):
            if not pdir.is_dir():
                continue
            versions = sorted([v for v in pdir.iterdir() if v.is_dir()])
            if not versions:
                continue
            latest = versions[-1]
            mfile = latest / "manifest.json"
            if not mfile.exists():
                continue
            raw_m = json.loads(mfile.read_text(encoding="utf-8"))
            sfile = latest / "schema_manifest.json"
            raw_sm = json.loads(sfile.read_text(encoding="utf-8")) if sfile.exists() else None
            jschemas: dict[str, dict[str, Any]] = {}
            js_dir = latest / "json_schemas"
            if js_dir.exists():
                for jf in sorted(js_dir.glob("*.schema.json")):
                    tname = jf.name.removesuffix(".schema.json")
                    jschemas[tname] = json.loads(jf.read_text(encoding="utf-8"))

            bundle = LoadedBundle(
                plugin_id=raw_m["plugin_id"],
                version=raw_m["version"],
                db_type=raw_m.get("db_type"),
                schema_name=raw_sm["schema"] if raw_sm else None,
                schema_version=raw_sm["schema_version"] if raw_sm else None,
                json_schemas=jschemas,
                raw_manifest=raw_m,
                raw_schema_manifest=raw_sm,
            )
            loaded[bundle.plugin_id] = bundle
        self._by_plugin = loaded

    def get(self, plugin_id: str) -> LoadedBundle | None:
        return self._by_plugin.get(plugin_id)

    def all_bundles(self) -> list[LoadedBundle]:
        return list(self._by_plugin.values())
