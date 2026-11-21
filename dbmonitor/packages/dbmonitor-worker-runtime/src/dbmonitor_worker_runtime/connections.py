from __future__ import annotations

import threading
import time
from typing import Any

from dbmonitor_sdk.models.target import DatabaseTarget


class PooledConnectionProvider:
    """Persistent connection reuse for high_frequency pool; per-task connections for low_frequency."""

    def __init__(self, persistent: bool, idle_ttl_seconds: int = 300) -> None:
        self.persistent = persistent
        self.idle_ttl_seconds = idle_ttl_seconds
        self._lock = threading.Lock()
        self._pool: dict[str, tuple[float, dict[str, Any]]] = {}
        self.cache_hits = 0
        self.cache_misses = 0

    def acquire(self, target: DatabaseTarget, credentials: dict[str, str]) -> dict[str, Any]:
        if self.persistent:
            now = time.time()
            with self._lock:
                entry = self._pool.get(target.server_id)
                if entry is not None and entry[0] > now:
                    self.cache_hits += 1
                    return entry[1]
                self.cache_misses += 1
            conn = {
                "server_id": target.server_id,
                "address": target.address,
                "port": target.port,
                "db_type": target.db_type,
                "opened_at": now,
                "reused": False,
            }
            return conn

        self.cache_misses += 1
        return {
            "server_id": target.server_id,
            "address": target.address,
            "port": target.port,
            "db_type": target.db_type,
            "opened_at": time.time(),
            "reused": False,
        }

    def release(self, target: DatabaseTarget, conn: Any, broken: bool = False) -> None:
        if not self.persistent or broken:
            with self._lock:
                self._pool.pop(target.server_id, None)
            return
        with self._lock:
            conn["reused"] = True
            self._pool[target.server_id] = (time.time() + self.idle_ttl_seconds, conn)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "active_cached": len(self._pool),
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
            }
