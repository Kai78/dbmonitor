from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in [
    ROOT / "packages" / "dbmonitor-common" / "src",
    ROOT / "packages" / "dbmonitor-sdk" / "src",
    ROOT / "packages" / "dbmonitor-platform-db" / "src",
    ROOT / "packages" / "dbmonitor-worker-runtime" / "src",
    ROOT / "services" / "api" / "src",
    ROOT / "services" / "plugin-registry" / "src",
    ROOT / "services" / "scheduler" / "src",
    ROOT / "services" / "inventory" / "src",
    ROOT / "services" / "results-processor" / "src",
    ROOT / "services" / "schema-migrator" / "src",
    ROOT / "tools",
]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from export_plugin_bundles import export_all

from dbmonitor_api.app import ApiContext, create_http_server
from dbmonitor_common.broker import RabbitMQBroker
from dbmonitor_inventory.consumers import InventoryConsumer
from dbmonitor_inventory.target_api import fetch_scoped_target
from dbmonitor_migrator.platform_migrations import apply_platform_migrations
from dbmonitor_migrator.plugin_runner import apply_plugin_bundle_migrations
from dbmonitor_platform_db.database import PlatformDatabase
from dbmonitor_platform_db.seed import seed_platform_defaults
from dbmonitor_registry.service import sync_bundles_to_registry
from dbmonitor_results.bundle_loader import BundleStore
from dbmonitor_results.consumers import ResultsProcessorConsumer
from dbmonitor_scheduler.outbox_relay import OutboxRelay
from dbmonitor_scheduler.ticker import SchedulerTicker
from dbmonitor_worker_runtime.tasks.discovery import DiscoveryWorker
from dbmonitor_worker_runtime.tasks.poll import PollerWorker


class EndToEndPipelineTests(unittest.TestCase):
    def test_discovery_to_metrics_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bundle_dir = tmp_path / "bundles"
            export_all(bundle_dir)
            db = PlatformDatabase(tmp_path / "test.sqlite3")
            apply_platform_migrations(db)
            apply_plugin_bundle_migrations(db, bundle_dir)
            sync_bundles_to_registry(db, bundle_dir)
            seed_platform_defaults(db)

            broker = RabbitMQBroker()
            bundles = BundleStore(bundle_dir)
            ctx = ApiContext(
                db=db,
                broker=broker,
                bundle_dir=bundle_dir,
                callbacks={"get_target_scoped": lambda sid, dbt: fetch_scoped_target(db, sid, dbt)},
            )
            srv = create_http_server("127.0.0.1", 0, ctx)
            port = srv.server_address[1]
            t_srv = threading.Thread(target=srv.serve_forever, daemon=True)
            t_srv.start()

            try:
                scheduler = SchedulerTicker(db)
                relay = OutboxRelay(db, broker)
                disc_worker = DiscoveryWorker(broker)
                inv_consumer = InventoryConsumer(db, broker)
                pg_hf = PollerWorker(
                    db_type="postgresql",
                    pool="high_frequency",
                    broker=broker,
                    inventory_base_url=f"http://127.0.0.1:{port}",
                )
                rp_hf = ResultsProcessorConsumer(pool="high_frequency", db=db, broker=broker, bundles=bundles)

                # Step 1: Schedule discovery & relay
                scheduler.tick_once()
                relay.relay_once()
                while (msg := broker.consume("discovery.run")) is not None:
                    disc_worker.process_one(msg)
                while (msg := broker.consume("discovery.results")) is not None:
                    from dbmonitor_inventory.reconciliation import reconcile_discovery_result
                    reconcile_discovery_result(db, msg.payload)
                    broker.ack(msg.message_id)

                with db.read() as conn:
                    srv_count = conn.execute("SELECT COUNT(*) FROM platform_database_servers").fetchone()[0]
                    self.assertGreaterEqual(srv_count, 5)

                # Step 2: Allow jittered assignments to become due, then schedule & poll PG HF
                time.sleep(3.2)
                scheduler.tick_once()
                relay.relay_once()
                while (msg := broker.consume("poll.postgresql.high_frequency")) is not None:
                    pg_hf.process_one(msg)
                while (msg := broker.consume("results.high_frequency")) is not None:
                    from dbmonitor_results.ingest import process_result_message
                    process_result_message(db, bundles, msg.payload)
                    broker.ack(msg.message_id)

                with db.read() as conn:
                    health_rows = conn.execute(
                        "SELECT COUNT(*) FROM reporting_instance_health WHERE db_type = 'postgresql'"
                    ).fetchone()[0]
                    self.assertGreaterEqual(health_rows, 1)
            finally:
                srv.shutdown()
                db.close()


if __name__ == "__main__":
    unittest.main()
