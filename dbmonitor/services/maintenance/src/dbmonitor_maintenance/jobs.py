from __future__ import annotations

import threading
import time
from datetime import timedelta

from dbmonitor_common.identifiers import new_uuid, utc_now, utc_now_iso
from dbmonitor_common.logging import get_logger
from dbmonitor_platform_db.database import PlatformDatabase

log = get_logger("maintenance")


class MaintenanceJobRunner:
    """Creates future partition entries ahead of time and prunes expired outbox/run rows."""

    def __init__(self, db: PlatformDatabase, interval_seconds: float = 30.0) -> None:
        self.db = db
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self.last_run_at: str | None = None
        self.pruned_rows = 0

    def run_once(self) -> dict[str, int]:
        now = utc_now()
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        created_partitions = 0
        pruned_outbox = 0

        with self.db.transaction() as conn:
            # Ensure 3 days of future partition headroom for every tracked table
            distinct_tables = conn.execute(
                "SELECT DISTINCT schema_name, table_name, retention_days FROM platform_partition_catalog"
            ).fetchall()
            for row in distinct_tables:
                for offset in range(0, 4):
                    day = (now + timedelta(days=offset)).strftime("%Y-%m-%d")
                    part_name = f"{row['table_name']}_{day.replace('-', '')}"
                    cur = conn.execute(
                        """
                        INSERT OR IGNORE INTO platform_partition_catalog (
                            partition_id, schema_name, table_name, partition_name,
                            range_start, range_end, retention_days, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            new_uuid(),
                            row["schema_name"],
                            row["table_name"],
                            part_name,
                            f"{day}T00:00:00Z",
                            f"{day}T23:59:59Z",
                            int(row["retention_days"]),
                            now_iso,
                        ),
                    )
                    created_partitions += cur.rowcount

            # Prune published outbox rows older than 1 hour
            cutoff = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            cur = conn.execute(
                "DELETE FROM platform_outbox WHERE published_at IS NOT NULL AND published_at < ?",
                (cutoff,),
            )
            pruned_outbox = cur.rowcount

        self.last_run_at = now_iso
        self.pruned_rows += pruned_outbox
        if created_partitions or pruned_outbox:
            log.info(
                "maintenance_cycle_completed",
                created_partitions=created_partitions,
                pruned_outbox=pruned_outbox,
            )
        return {
            "created_partitions": created_partitions,
            "pruned_outbox": pruned_outbox,
        }

    def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as exc:
                log.error("maintenance_error", error=str(exc))
            time.sleep(self.interval_seconds)

    def stop(self) -> None:
        self._stop.set()
