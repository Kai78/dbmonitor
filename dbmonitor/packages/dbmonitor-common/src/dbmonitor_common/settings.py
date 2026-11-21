from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlatformSettings:
    root_dir: Path
    db_path: Path
    bundle_dir: Path
    api_host: str
    api_port: int
    platform_min_interval_seconds: int = 30
    max_result_bytes: int = 1_048_576
    scheduler_tick_seconds: float = 0.5
    outbox_relay_tick_seconds: float = 0.25
    reaper_tick_seconds: float = 1.0
    default_max_concurrency_per_server: int = 2
    secret_cache_ttl_seconds: int = 300
    hf_connection_idle_ttl_seconds: int = 300


def get_settings() -> PlatformSettings:
    root_dir = Path(
        os.environ.get(
            "DBMONITOR_ROOT",
            str(Path(__file__).resolve().parents[4]),
        )
    )
    data_dir = root_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(os.environ.get("DBMONITOR_DB_PATH", str(data_dir / "dbmonitor.sqlite3")))
    bundle_dir = Path(
        os.environ.get("DBMONITOR_BUNDLE_DIR", str(root_dir / "build" / "plugin-bundles"))
    )
    return PlatformSettings(
        root_dir=root_dir,
        db_path=db_path,
        bundle_dir=bundle_dir,
        api_host=os.environ.get("DBMONITOR_API_HOST", "127.0.0.1"),
        api_port=int(os.environ.get("DBMONITOR_API_PORT", "8000")),
        platform_min_interval_seconds=int(
            os.environ.get("DBMONITOR_PLATFORM_MIN_INTERVAL_SECONDS", "30")
        ),
        max_result_bytes=int(os.environ.get("DBMONITOR_MAX_RESULT_BYTES", "1048576")),
    )
