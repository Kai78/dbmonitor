from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from dbmonitor_common.broker import BrokerMessage, RabbitMQBroker
from dbmonitor_common.identifiers import new_uuid, parse_iso, utc_now, utc_now_iso
from dbmonitor_common.logging import get_logger
from dbmonitor_sdk.errors import ErrorCategory, PermanentPluginError, TransientPluginError
from dbmonitor_worker_runtime.connections import PooledConnectionProvider
from dbmonitor_worker_runtime.credentials import SecretsManagerClient
from dbmonitor_worker_runtime.loader import LoadedPoller, load_poller_worker_plugin
from dbmonitor_worker_runtime.results import build_failure_envelope, build_result_envelope
from dbmonitor_worker_runtime.targets import TargetConfigClient

log = get_logger("worker-runtime.poll")


@dataclass
class _RuntimePollContext:
    run_id: str
    attempt: int
    profile: str
    pool: str
    collector_groups: list[str]
    deadline: datetime
    connections: PooledConnectionProvider
    credentials: SecretsManagerClient


class PollerWorker:
    """One deployment per (db_type, pool) consuming poll.{db_type}.{pool}."""

    def __init__(
        self,
        *,
        db_type: str,
        pool: str,
        broker: RabbitMQBroker,
        inventory_base_url: str,
        task_timeout_seconds: int = 20,
        emit_started_events: bool = False,
        max_result_bytes: int = 1_048_576,
    ) -> None:
        self.db_type = db_type
        self.pool = pool
        self.broker = broker
        self.queue = f"poll.{db_type}.{pool}"
        self.results_queue = f"results.{pool}"
        self.task_timeout_seconds = task_timeout_seconds
        self.emit_started_events = emit_started_events
        self.max_result_bytes = max_result_bytes

        self.loaded: LoadedPoller = load_poller_worker_plugin(db_type, pool)
        self.targets = TargetConfigClient(inventory_base_url, worker_db_type=db_type)
        self.credentials = SecretsManagerClient(ttl_seconds=300)
        self.connections = PooledConnectionProvider(
            persistent=(pool == "high_frequency"),
            idle_ttl_seconds=300,
        )
        self.broker.declare_queue(self.queue)
        self.broker.declare_queue(self.results_queue)
        self._stop = threading.Event()
        self.processed_count = 0
        self.expired_count = 0

    def process_one(self, msg: BrokerMessage) -> None:
        payload = msg.payload
        run_id = payload.get("polling_run_id", "")

        # 1. Task expiry check: never emit stale data late
        if self.broker.is_expired(msg):
            self.expired_count += 1
            self.broker.discard_expired(msg.message_id)
            log.info(
                "poll_task_expired_discarded",
                polling_run_id=run_id,
                db_type=self.db_type,
                pool=self.pool,
            )
            return

        # 2. Startup/receipt routing validation
        if payload.get("db_type") != self.db_type or payload.get("pool") != self.pool:
            self.broker.nack(
                msg.message_id,
                requeue=False,
                reason="worker_routing_mismatch",
            )
            log.error(
                "worker_routing_mismatch",
                polling_run_id=run_id,
                expected=f"{self.db_type}.{self.pool}",
                got=f"{payload.get('db_type')}.{payload.get('pool')}",
            )
            return

        # 3. Optional started event (LF & manual runs)
        if self.emit_started_events or payload.get("trigger") == "manual":
            self.broker.publish(
                self.results_queue,
                {
                    "event_type": "started",
                    "message_id": new_uuid(),
                    "polling_run_id": run_id,
                    "started_at": utc_now_iso(),
                },
            )

        started_at = utc_now_iso()
        server_id = payload["server_id"]
        config_version = int(payload.get("config_version", 1))
        groups = list(payload.get("collector_groups", []))
        max_attempts = int(payload.get("max_attempts", 1))
        expires_at = parse_iso(payload["expires_at"]) if payload.get("expires_at") else utc_now() + timedelta(seconds=60)

        try:
            target = self.targets.get_target(server_id, config_version)
        except Exception as exc:
            env = build_failure_envelope(
                polling_run_id=run_id,
                server_id=server_id,
                db_type=self.db_type,
                plugin_id=self.loaded.manifest.plugin_id,
                plugin_version=self.loaded.manifest.version,
                schema_version=self.loaded.manifest.schema_version or "0001",
                profile=payload["profile"],
                pool=self.pool,
                attempt_count=int(payload.get("attempt", 1)),
                started_at=started_at,
                finished_at=utc_now_iso(),
                error_category=ErrorCategory.INVALID_CONFIGURATION.value,
                error_message=str(exc),
            )
            self.broker.publish(self.results_queue, env.to_dict())
            self.broker.ack(msg.message_id)
            return

        fault = target.metadata.get("fault_mode", "none")
        if fault == "worker_crash":
            # Simulate abrupt worker crash before ack/result so reaper detects expired lease
            log.warning(
                "simulated_worker_crash",
                polling_run_id=run_id,
                server_id=server_id,
                db_type=self.db_type,
                pool=self.pool,
            )
            return

        attempt = int(payload.get("attempt", 1))
        last_error: Exception | None = None
        while attempt <= max_attempts:
            if utc_now() >= expires_at:
                self.expired_count += 1
                self.broker.discard_expired(msg.message_id)
                return

            deadline = min(
                utc_now() + timedelta(seconds=self.task_timeout_seconds),
                expires_at,
            )
            ctx = _RuntimePollContext(
                run_id=run_id,
                attempt=attempt,
                profile=payload["profile"],
                pool=self.pool,
                collector_groups=groups,
                deadline=deadline,
                connections=self.connections,
                credentials=self.credentials,
            )
            try:
                poll_res = self.loaded.plugin.poll(target, ctx)
                schema_ver = (
                    "9999"
                    if fault == "schema_ahead"
                    else (self.loaded.manifest.schema_version or "0001")
                )
                envelope = build_result_envelope(
                    polling_run_id=run_id,
                    server_id=server_id,
                    db_type=self.db_type,
                    plugin_id=self.loaded.manifest.plugin_id,
                    plugin_version=self.loaded.manifest.version,
                    schema_version=schema_ver,
                    profile=payload["profile"],
                    pool=self.pool,
                    attempt_count=attempt,
                    started_at=started_at,
                    finished_at=utc_now_iso(),
                    poll_result=poll_res,
                    max_result_bytes=self.max_result_bytes,
                )
                self.broker.publish(self.results_queue, envelope.to_dict())
                self.broker.ack(msg.message_id)
                self.processed_count += 1
                return
            except PermanentPluginError as exc:
                last_error = exc
                break
            except TransientPluginError as exc:
                last_error = exc
                if attempt >= max_attempts or self.pool == "high_frequency":
                    break
                attempt += 1
                backoff = min(1.5, 0.25 * (2 ** (attempt - 1)))
                time.sleep(backoff)
            except Exception as exc:
                last_error = exc
                break

        err_cat = getattr(last_error, "category", ErrorCategory.INTERNAL_ERROR)
        err_cat_val = err_cat.value if hasattr(err_cat, "value") else str(err_cat)
        fail_env = build_failure_envelope(
            polling_run_id=run_id,
            server_id=server_id,
            db_type=self.db_type,
            plugin_id=self.loaded.manifest.plugin_id,
            plugin_version=self.loaded.manifest.version,
            schema_version=self.loaded.manifest.schema_version or "0001",
            profile=payload["profile"],
            pool=self.pool,
            attempt_count=attempt,
            started_at=started_at,
            finished_at=utc_now_iso(),
            error_category=err_cat_val,
            error_message=str(last_error),
        )
        self.broker.publish(self.results_queue, fail_env.to_dict())
        self.broker.ack(msg.message_id)
        self.processed_count += 1

    def run_forever(self) -> None:
        while not self._stop.is_set():
            msg = self.broker.consume(self.queue)
            if msg is None:
                time.sleep(0.1)
                continue
            self.process_one(msg)

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict:
        return {
            "worker_id": f"poller-{self.db_type}-{self.pool}",
            "db_type": self.db_type,
            "pool": self.pool,
            "queue": self.queue,
            "plugin_id": self.loaded.manifest.plugin_id,
            "plugin_version": self.loaded.manifest.version,
            "processed_count": self.processed_count,
            "expired_count": self.expired_count,
            "connections": self.connections.stats(),
            "target_cache": {
                "hits": self.targets.hits,
                "misses": self.targets.misses,
            },
            "secret_cache": {
                "hits": self.credentials.hits,
                "misses": self.credentials.misses,
            },
        }
