from __future__ import annotations

import threading
import time

from dbmonitor_common.identifiers import utc_now_iso
from dbmonitor_common.logging import get_logger
from dbmonitor_platform_db.database import PlatformDatabase

log = get_logger("scheduler.reaper")


class LeaseReaper:
    """Recovers expired leases and marks expired/lost runs without stranding assignments."""

    def __init__(self, db: PlatformDatabase, tick_seconds: float = 1.0) -> None:
        self.db = db
        self.tick_seconds = tick_seconds
        self._stop = threading.Event()
        self.reaped_total = 0

    def reap_once(self) -> int:
        now_iso = utc_now_iso()
        reaped = 0

        with self.db.transaction() as conn:
            # 1. Runs whose task expiry window has passed while still queued
            expired_queued = conn.execute(
                """
                SELECT polling_run_id, assignment_id
                FROM platform_polling_runs
                WHERE status = 'queued' AND expires_at IS NOT NULL AND expires_at < ?
                LIMIT 100
                """,
                (now_iso,),
            ).fetchall()
            for r in expired_queued:
                conn.execute(
                    """
                    UPDATE platform_polling_runs
                    SET status = 'expired', error_category = 'task_expired',
                        error_message = 'Task expired before execution could start',
                        finished_at = ?
                    WHERE polling_run_id = ?
                    """,
                    (now_iso, r["polling_run_id"]),
                )
                if r["assignment_id"]:
                    conn.execute(
                        """
                        UPDATE platform_polling_state
                        SET lease_owner = NULL, lease_expires_at = NULL,
                            missed_interval_count = missed_interval_count + 1
                        WHERE assignment_id = ?
                        """,
                        (r["assignment_id"],),
                    )
                reaped += 1

            # 2. Expired leases on polling_state where run never produced a terminal result (e.g. worker crash)
            expired_leases = conn.execute(
                """
                SELECT assignment_id, last_run_id
                FROM platform_polling_state
                WHERE lease_expires_at IS NOT NULL AND lease_expires_at < ?
                """,
                (now_iso,),
            ).fetchall()
            for st in expired_leases:
                if st["last_run_id"]:
                    run_row = conn.execute(
                        "SELECT status FROM platform_polling_runs WHERE polling_run_id = ?",
                        (st["last_run_id"],),
                    ).fetchone()
                    if run_row and run_row["status"] in ("queued", "running"):
                        conn.execute(
                            """
                            UPDATE platform_polling_runs
                            SET status = 'lost', error_category = 'lease_expired',
                                error_message = 'Worker lease expired without terminal result',
                                finished_at = ?
                            WHERE polling_run_id = ?
                            """,
                            (now_iso, st["last_run_id"]),
                        )
                conn.execute(
                    """
                    UPDATE platform_polling_state
                    SET lease_owner = NULL, lease_expires_at = NULL,
                        consecutive_failures = consecutive_failures + 1
                    WHERE assignment_id = ?
                    """,
                    (st["assignment_id"],),
                )
                reaped += 1

            # 3. Expired discovery provider leases
            conn.execute(
                """
                UPDATE platform_provider_instances
                SET lease_owner = NULL, lease_expires_at = NULL
                WHERE lease_expires_at IS NOT NULL AND lease_expires_at < ?
                """,
                (now_iso,),
            )

        if reaped > 0:
            self.reaped_total += reaped
            log.info("leases_and_runs_reaped", count=reaped)
        return reaped

    def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self.reap_once()
            except Exception as exc:
                log.error("reaper_error", error=str(exc))
            time.sleep(self.tick_seconds)

    def stop(self) -> None:
        self._stop.set()
