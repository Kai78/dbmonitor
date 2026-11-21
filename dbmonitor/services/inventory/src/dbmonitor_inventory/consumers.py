from __future__ import annotations

import threading
import time

from dbmonitor_common.broker import RabbitMQBroker
from dbmonitor_common.logging import get_logger
from dbmonitor_inventory.reconciliation import reconcile_discovery_result
from dbmonitor_platform_db.database import PlatformDatabase

log = get_logger("inventory.consumer")


class InventoryConsumer:
    def __init__(self, db: PlatformDatabase, broker: RabbitMQBroker) -> None:
        self.db = db
        self.broker = broker
        self.broker.declare_queue("discovery.results")
        self._stop = threading.Event()

    def run_forever(self) -> None:
        while not self._stop.is_set():
            msg = self.broker.consume("discovery.results")
            if msg is None:
                time.sleep(0.1)
                continue
            try:
                reconcile_discovery_result(self.db, msg.payload)
                self.broker.ack(msg.message_id)
            except Exception as exc:
                log.error("inventory_reconcile_error", error=str(exc))
                self.broker.nack(msg.message_id, requeue=False, reason=str(exc))

    def stop(self) -> None:
        self._stop.set()
