from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Any

from dbmonitor_common.logging import get_logger
from dbmonitor_sdk.models.target import DatabaseTarget

log = get_logger("worker-runtime.targets")


class TargetConfigClient:
    """Fetches DatabaseTarget via authenticated Inventory Target-Config API and caches by config_version."""

    def __init__(self, inventory_base_url: str, worker_db_type: str) -> None:
        self.inventory_base_url = inventory_base_url.rstrip("/")
        self.worker_db_type = worker_db_type
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, int], DatabaseTarget] = {}
        self.hits = 0
        self.misses = 0

    def get_target(self, server_id: str, config_version: int) -> DatabaseTarget:
        key = (server_id, int(config_version))
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self.hits += 1
                return cached
            self.misses += 1

        url = f"{self.inventory_base_url}/api/internal/targets/{server_id}"
        req = urllib.request.Request(
            url,
            headers={
                "X-Worker-Db-Type": self.worker_db_type,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"Inventory API rejected target fetch for {server_id}: HTTP {exc.code}"
            ) from exc

        target = DatabaseTarget.from_dict(data)
        if target.db_type != self.worker_db_type:
            raise RuntimeError(
                f"Scope mismatch: worker '{self.worker_db_type}' received target '{target.db_type}'."
            )
        with self._lock:
            # Evict older versions for this server_id
            stale_keys = [k for k in self._cache if k[0] == server_id and k[1] != target.config_version]
            for sk in stale_keys:
                self._cache.pop(sk, None)
            self._cache[(server_id, target.config_version)] = target
        return target
