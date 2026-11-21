#!/usr/bin/env python3
"""Composition root launching all DBMonitor services and isolated worker pools."""
from __future__ import annotations

import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent

# Add workspace package source trees to sys.path
_SRC_PATHS = [
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
    ROOT / "services" / "maintenance" / "src",
    ROOT / "plugins" / "providers" / "cmdb" / "src",
    ROOT / "plugins" / "providers" / "cloud" / "src",
    ROOT / "plugins" / "pollers" / "postgresql" / "src",
    ROOT / "plugins" / "pollers" / "oracle" / "src",
    ROOT / "plugins" / "pollers" / "mssql" / "src",
    ROOT / "tools",
]
for sp in _SRC_PATHS:
    if str(sp) not in sys.path:
        sys.path.insert(0, str(sp))

from check_import_boundaries import check_boundaries
from export_plugin_bundles import export_all
from generate_rabbitmq_topology import write_topology

from dbmonitor_api.app import ApiContext, create_http_server
from dbmonitor_common.broker import RabbitMQBroker
from dbmonitor_common.logging import get_logger
from dbmonitor_common.settings import get_settings
from dbmonitor_inventory.consumers import InventoryConsumer
from dbmonitor_inventory.target_api import fetch_scoped_target
from dbmonitor_maintenance.jobs import MaintenanceJobRunner
from dbmonitor_migrator.platform_migrations import apply_platform_migrations
from dbmonitor_migrator.plugin_runner import apply_plugin_bundle_migrations
from dbmonitor_platform_db.database import PlatformDatabase
from dbmonitor_platform_db.seed import seed_platform_defaults
from dbmonitor_poller_mssql.manifest import MANIFEST as MSSQL_M
from dbmonitor_poller_mssql.plugin import plugin as MSSQL_P
from dbmonitor_poller_oracle.manifest import MANIFEST as ORACLE_M
from dbmonitor_poller_oracle.plugin import plugin as ORACLE_P
from dbmonitor_poller_postgresql.manifest import MANIFEST as PG_M
from dbmonitor_poller_postgresql.plugin import plugin as PG_P
from dbmonitor_provider_cloud.manifest import MANIFEST as CLOUD_M
from dbmonitor_provider_cloud.plugin import plugin as CLOUD_P
from dbmonitor_provider_cmdb.manifest import MANIFEST as CMDB_M
from dbmonitor_provider_cmdb.plugin import plugin as CMDB_P
from dbmonitor_registry.service import sync_bundles_to_registry
from dbmonitor_results.bundle_loader import BundleStore
from dbmonitor_results.consumers import ResultsProcessorConsumer
from dbmonitor_scheduler.outbox_relay import OutboxRelay
from dbmonitor_scheduler.reaper import LeaseReaper
from dbmonitor_scheduler.ticker import SchedulerTicker
from dbmonitor_sdk.contracts.schema import SchemaManifest
from dbmonitor_sdk.testing import (
    verify_poller_contract,
    verify_profile_contract,
    verify_provider_contract,
    verify_schema_contract,
)
from dbmonitor_worker_runtime.tasks.discovery import DiscoveryWorker
from dbmonitor_worker_runtime.tasks.poll import PollerWorker

import json

log = get_logger("platform")


def run_all_ci_checks(bundle_dir: Path) -> dict[str, Any]:
    boundaries = check_boundaries()
    plugin_reports: list[dict[str, Any]] = []

    for prov_plugin, prov_manifest in ((CMDB_P, CMDB_M), (CLOUD_P, CLOUD_M)):
        checks = verify_provider_contract(prov_plugin, prov_manifest)
        plugin_reports.append(
            {
                "plugin_id": prov_manifest.plugin_id,
                "kind": "provider",
                "passed": True,
                "checks": checks,
            }
        )

    poller_specs = [
        (PG_P, PG_M, ROOT / "plugins" / "pollers" / "postgresql" / "src" / "dbmonitor_poller_postgresql" / "schema" / "manifest.json"),
        (ORACLE_P, ORACLE_M, ROOT / "plugins" / "pollers" / "oracle" / "src" / "dbmonitor_poller_oracle" / "schema" / "manifest.json"),
        (MSSQL_P, MSSQL_M, ROOT / "plugins" / "pollers" / "mssql" / "src" / "dbmonitor_poller_mssql" / "schema" / "manifest.json"),
    ]
    for p_plugin, p_manifest, sm_path in poller_specs:
        sm = SchemaManifest.from_dict(json.loads(sm_path.read_text(encoding="utf-8")))
        checks = (
            verify_poller_contract(p_plugin, p_manifest)
            + verify_profile_contract(p_manifest)
            + verify_schema_contract(sm)
        )
        plugin_reports.append(
            {
                "plugin_id": p_manifest.plugin_id,
                "kind": "poller",
                "db_type": p_manifest.db_type,
                "passed": True,
                "checks": checks,
            }
        )

    return {
        "import_boundaries": boundaries,
        "contract_tests": plugin_reports,
        "all_passed": boundaries["passed"] and all(r["passed"] for r in plugin_reports),
    }


def main() -> None:
    settings = get_settings()

    # 1. Build data-only plugin bundles and RabbitMQ topology artifact
    export_all(settings.bundle_dir)
    write_topology()

    # 2. Initialize central DB & run platform + plugin bundle migrations
    db = PlatformDatabase(settings.db_path)
    apply_platform_migrations(db)
    apply_plugin_bundle_migrations(db, settings.bundle_dir)
    sync_bundles_to_registry(db, settings.bundle_dir)
    seed_platform_defaults(db)

    broker = RabbitMQBroker()
    bundles = BundleStore(settings.bundle_dir)
    inventory_base_url = f"http://{settings.api_host}:{settings.api_port}"

    # 3. Instantiate services & isolated worker pools
    scheduler = SchedulerTicker(db, tick_seconds=settings.scheduler_tick_seconds)
    outbox_relay = OutboxRelay(db, broker, tick_seconds=settings.outbox_relay_tick_seconds)
    reaper = LeaseReaper(db, tick_seconds=settings.reaper_tick_seconds)
    inventory_consumer = InventoryConsumer(db, broker)
    discovery_worker = DiscoveryWorker(broker)
    maintenance = MaintenanceJobRunner(db, interval_seconds=30.0)

    results_processors = [
        ResultsProcessorConsumer(pool="high_frequency", db=db, broker=broker, bundles=bundles),
        ResultsProcessorConsumer(pool="low_frequency", db=db, broker=broker, bundles=bundles),
    ]

    poller_workers: list[PollerWorker] = []
    for db_type in ("postgresql", "oracle", "mssql"):
        poller_workers.append(
            PollerWorker(
                db_type=db_type,
                pool="high_frequency",
                broker=broker,
                inventory_base_url=inventory_base_url,
                task_timeout_seconds=20,
                emit_started_events=False,
                max_result_bytes=settings.max_result_bytes,
            )
        )
        poller_workers.append(
            PollerWorker(
                db_type=db_type,
                pool="low_frequency",
                broker=broker,
                inventory_base_url=inventory_base_url,
                task_timeout_seconds=120,
                emit_started_events=True,
                max_result_bytes=settings.max_result_bytes,
            )
        )

    # 4. Start API server first so Inventory Target-Config API is ready for workers
    api_ctx = ApiContext(
        db=db,
        broker=broker,
        bundle_dir=settings.bundle_dir,
        callbacks={
            "get_target_scoped": lambda sid, dbt: fetch_scoped_target(db, sid, dbt),
            "get_worker_statuses": lambda: [w.status() for w in poller_workers],
            "get_processor_statuses": lambda: [rp.status() for rp in results_processors],
            "run_ci_checks": lambda: run_all_ci_checks(settings.bundle_dir),
            "run_maintenance": lambda: maintenance.run_once(),
        },
    )
    http_server = create_http_server(settings.api_host, settings.api_port, api_ctx)

    threads: list[threading.Thread] = [
        threading.Thread(target=http_server.serve_forever, name="api-http", daemon=True),
        threading.Thread(target=scheduler.run_forever, name="scheduler-ticker", daemon=True),
        threading.Thread(target=outbox_relay.run_forever, name="outbox-relay", daemon=True),
        threading.Thread(target=reaper.run_forever, name="lease-reaper", daemon=True),
        threading.Thread(target=inventory_consumer.run_forever, name="inventory-consumer", daemon=True),
        threading.Thread(target=discovery_worker.run_forever, name="discovery-worker", daemon=True),
        threading.Thread(target=maintenance.run_forever, name="maintenance-jobs", daemon=True),
        *[
            threading.Thread(target=rp.run_forever, name=f"results-{rp.pool}", daemon=True)
            for rp in results_processors
        ],
        *[
            threading.Thread(target=pw.run_forever, name=f"poller-{pw.db_type}-{pw.pool}", daemon=True)
            for pw in poller_workers
        ],
    ]

    for t in threads:
        t.start()

    # Kick off an immediate maintenance pass
    maintenance.run_once()

    log.info(
        "platform_started",
        api_url=inventory_base_url,
        worker_pools=len(poller_workers),
        results_processors=len(results_processors),
    )

    stop_event = threading.Event()

    def _shutdown(signum: int, frame: Any) -> None:
        log.info("platform_shutting_down", signal=signum)
        scheduler.stop()
        outbox_relay.stop()
        reaper.stop()
        inventory_consumer.stop()
        discovery_worker.stop()
        maintenance.stop()
        for rp in results_processors:
            rp.stop()
        for pw in poller_workers:
            pw.stop()
        http_server.shutdown()
        db.close()
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    while not stop_event.is_set():
        time.sleep(0.5)


if __name__ == "__main__":
    main()
