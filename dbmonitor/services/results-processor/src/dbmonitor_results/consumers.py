from __future__ import annotations

import threading
import time

from dbmonitor_common.broker import RabbitMQBroker
from dbmonitor_common.logging import get_logger
from dbmonitor_platform_db.database import PlatformDatabase
from dbmonitor_results.bundle_loader import BundleStore
from dbmonitor_results.ingest import SchemaNotReadyError, process_result_message

log = get_logger("results-processor.consumer")


class ResultsProcessorConsumer:
    """Dedicated results processor deployment per pool (results.{pool}) so LF never delays HF."""

    def __init__(
        self,
        *,
        pool: str,
        db: PlatformDatabase,
        broker: RabbitMQBroker,
        bundles: BundleStore,
    ) -> None:
        self.pool = pool
        self.queue = f"results.{pool}"
        self.db = db
        self.broker = broker
        self.bundles = bundles
        self.broker.declare_queue(self.queue)
        self._stop = threading.Event()
        self.processed_count = 0
        self.rejected_count = 0
        self.schema_not_ready_count = 0

    def run_forever(self) -> None:
        while not self._stop.is_set():
            msg = self.broker.consume(self.queue)
            if msg is None:
                time.sleep(0.08)
                continue
            try:
                process_result_message(self.db, self.bundles, msg.payload)
                self.broker.ack(msg.message_id)
                self.processed_count += 1
            except SchemaNotReadyError as exc:
                self.schema_not_ready_count += 1
                if msg.attempts < 3:
                    time.sleep(0.2)
                    self.broker.nack(msg.message_id, requeue=True, reason="schema_not_ready")
                else:
                    self.broker.nack(msg.message_id, requeue=False, reason="schema_not_ready")
                    log.error("result_dead_lettered_schema_not_ready", error=str(exc))
            except Exception as exc:
                self.rejected_count += 1
                self.broker.nack(msg.message_id, requeue=False, reason=str(exc))
                log.error("result_ingestion_rejected", pool=self.pool, error=str(exc))

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict:
        return {
            "pool": self.pool,
            "queue": self.queue,
            "processed_count": self.processed_count,
            "rejected_count": self.rejected_count,
            "schema_not_ready_count": self.schema_not_ready_count,
        }
