from __future__ import annotations

import threading
import time


class SecretsManagerClient:
    """Resolves secret:// references with a short TTL cache. Never logs raw credentials."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, dict[str, str]]] = {}
        self.hits = 0
        self.misses = 0

    def resolve(self, secret_ref: str) -> dict[str, str]:
        now = time.time()
        with self._lock:
            entry = self._cache.get(secret_ref)
            if entry is not None and entry[0] > now:
                self.hits += 1
                return dict(entry[1])
            self.misses += 1

        # Deterministic synthetic resolution from secret_ref (never persisted or logged)
        creds = {
            "username": "dbmonitor_ro",
            "password": f"vault_ephemeral_{abs(hash(secret_ref)) % 100000:05d}",
            "secret_ref": secret_ref,
        }
        with self._lock:
            self._cache[secret_ref] = (now + self.ttl_seconds, creds)
        return dict(creds)
