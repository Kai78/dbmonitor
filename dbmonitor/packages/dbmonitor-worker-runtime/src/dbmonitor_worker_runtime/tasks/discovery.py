from __future__ import annotations

import threading
import time

from dbmonitor_common.broker import BrokerMessage, RabbitMQBroker
from dbmonitor_common.identifiers import new_uuid, utc_now_iso
from dbmonitor_common.logging import get_logger
from dbmonitor_sdk.models.server import DiscoveryContext
from dbmonitor_worker_runtime.loader import load_discovery_plugins

log = get_logger("worker-runtime.discovery")


class DiscoveryWorker:
    """Consumes discovery.run, executes provider plugins, publishes to discovery.results."""

    def __init__(self, broker: RabbitMQBroker) -> None:
        self.broker = broker
        self.plugins = load_discovery_plugins()
        self.broker.declare_queue("discovery.run")
        self.broker.declare_queue("discovery.results")
        self._stop = threading.Event()
        self.processed_count = 0

    def process_one(self, msg: BrokerMessage) -> None:
        payload = msg.payload
        run_id = payload["discovery_run_id"]
        plugin_id = payload["plugin_id"]
        plugin = self.plugins.get(plugin_id)

        if plugin is None:
            self.broker.publish(
                "discovery.results",
                {
                    "message_id": new_uuid(),
                    "discovery_run_id": run_id,
                    "provider_instance_id": payload["provider_instance_id"],
                    "provider_name": payload["provider_name"],
                    "status": "failed",
                    "error_message": f"Unknown provider plugin '{plugin_id}'",
                    "dry_run": bool(payload.get("dry_run", False)),
                    "servers": [],
                    "finished_at": utc_now_iso(),
                },
            )
            self.broker.ack(msg.message_id)
            return

        ctx = DiscoveryContext(
            run_id=run_id,
            provider_instance_id=payload["provider_instance_id"],
            provider_name=payload["provider_name"],
            config=dict(payload.get("config", {})),
            dry_run=bool(payload.get("dry_run", False)),
        )
        try:
            servers: list[dict] = []
            for page in plugin.discover(ctx):
                for item in page:
                    servers.append(item.to_dict())
            self.broker.publish(
                "discovery.results",
                {
                    "message_id": new_uuid(),
                    "discovery_run_id": run_id,
                    "provider_instance_id": payload["provider_instance_id"],
                    "provider_name": payload["provider_name"],
                    "status": "succeeded",
                    "error_message": None,
                    "dry_run": ctx.dry_run,
                    "servers": servers,
                    "finished_at": utc_now_iso(),
                },
            )
            self.broker.ack(msg.message_id)
            self.processed_count += 1
            log.info(
                "discovery_completed",
                discovery_run_id=run_id,
                plugin_id=plugin_id,
                discovered_count=len(servers),
                dry_run=ctx.dry_run,
            )
        except Exception as exc:
            self.broker.publish(
                "discovery.results",
                {
                    "message_id": new_uuid(),
                    "discovery_run_id": run_id,
                    "provider_instance_id": payload["provider_instance_id"],
                    "provider_name": payload["provider_name"],
                    "status": "failed",
                    "error_message": str(exc),
                    "dry_run": ctx.dry_run,
                    "servers": [],
                    "finished_at": utc_now_iso(),
                },
            )
            self.broker.ack(msg.message_id)

    def run_forever(self) -> None:
        while not self._stop.is_set():
            msg = self.broker.consume("discovery.run")
            if msg is None:
                time.sleep(0.1)
                continue
            self.process_one(msg)

    def stop(self) -> None:
        self._stop.set()
