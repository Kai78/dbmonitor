from __future__ import annotations

import json
import threading
import time

from dbmonitor_common.broker import RabbitMQBroker
from dbmonitor_common.identifiers import utc_now_iso
from dbmonitor_common.logging import get_logger
from dbmonitor_platform_db.database import PlatformDatabase

log = get_logger("scheduler.outbox_relay")


class OutboxRelay:
    """Publishes unpublished platform_outbox rows to RabbitMQ with publisher confirms."""

    def __init__(self, db: PlatformDatabase, broker: RabbitMQBroker, tick_seconds: float = 0.25) -> None:
        self.db = db
        self.broker = broker
        self.tick_seconds = tick_seconds
        self._stop = threading.Event()
        self.published_total = 0

    def relay_once(self) -> int:
        with self.db.read() as conn:
            rows = conn.execute(
                """
                SELECT outbox_id, queue_name, payload_json, expires_at
                FROM platform_outbox
                WHERE published_at IS NULL
                ORDER BY created_at ASC
                LIMIT 100
                """
            ).fetchall()

        if not rows:
            return 0

        published_ids: list[str] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            self.broker.publish(
                row["queue_name"],
                payload,
                message_id=payload.get("message_id"),
                expires_at=row["expires_at"],
            )
            published_ids.append(row["outbox_id"])

        now_iso = utc_now_iso()
        with self.db.transaction() as conn:
            for oid in published_ids:
                conn.execute(
                    "UPDATE platform_outbox SET published_at = ? WHERE outbox_id = ?",
                    (now_iso, oid),
                )
        self.published_total += len(published_ids)
        return len(published_ids)

    def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self.relay_once()
            except Exception as exc:
                log.error("outbox_relay_error", error=str(exc))
            time.sleep(self.tick_seconds)

    def stop(self) -> None:
        self._stop.set()
