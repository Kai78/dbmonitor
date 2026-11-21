from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from dbmonitor_common.identifiers import new_uuid, parse_iso, utc_now


@dataclass
class BrokerMessage:
    message_id: str
    queue: str
    payload: dict[str, Any]
    enqueued_at: float
    expires_at: str | None = None
    attempts: int = 0
    headers: dict[str, Any] = field(default_factory=dict)


class RabbitMQBroker:
    """Thread-safe RabbitMQ topology broker with quorum queues, DLQs, late acks, and expiry."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queues: dict[str, deque[BrokerMessage]] = defaultdict(deque)
        self._inflight: dict[str, BrokerMessage] = {}
        self._paused: set[str] = set()
        self._counters: dict[str, dict[str, int]] = defaultdict(
            lambda: {"published": 0, "acked": 0, "dead_lettered": 0, "expired": 0}
        )
        self._declared_queues: set[str] = set()

    def declare_queue(self, queue_name: str) -> None:
        with self._lock:
            self._declared_queues.add(queue_name)
            if not queue_name.startswith("dlq."):
                self._declared_queues.add(f"dlq.{queue_name}")

    def pause_queue(self, queue_name: str) -> None:
        with self._lock:
            self._paused.add(queue_name)

    def resume_queue(self, queue_name: str) -> None:
        with self._lock:
            self._paused.discard(queue_name)

    def is_paused(self, queue_name: str) -> bool:
        with self._lock:
            return queue_name in self._paused

    def publish(
        self,
        queue: str,
        payload: dict[str, Any],
        message_id: str | None = None,
        expires_at: str | None = None,
        headers: dict[str, Any] | None = None,
    ) -> str:
        msg_id = message_id or payload.get("message_id") or new_uuid()
        msg = BrokerMessage(
            message_id=msg_id,
            queue=queue,
            payload=dict(payload),
            enqueued_at=time.time(),
            expires_at=expires_at or payload.get("expires_at"),
            headers=dict(headers or {}),
        )
        with self._lock:
            self._declared_queues.add(queue)
            if not queue.startswith("dlq."):
                self._declared_queues.add(f"dlq.{queue}")
            self._queues[queue].append(msg)
            self._counters[queue]["published"] += 1
        return msg_id

    def consume(self, queue: str) -> BrokerMessage | None:
        with self._lock:
            if queue in self._paused:
                return None
            q = self._queues.get(queue)
            if not q:
                return None
            msg = q.popleft()
            msg.attempts += 1
            self._inflight[msg.message_id] = msg
            return msg

    def ack(self, message_id: str) -> None:
        with self._lock:
            msg = self._inflight.pop(message_id, None)
            if msg is not None:
                self._counters[msg.queue]["acked"] += 1

    def discard_expired(self, message_id: str) -> None:
        with self._lock:
            msg = self._inflight.pop(message_id, None)
            if msg is not None:
                self._counters[msg.queue]["expired"] += 1

    def nack(
        self,
        message_id: str,
        requeue: bool = False,
        reason: str = "rejected",
    ) -> None:
        with self._lock:
            msg = self._inflight.pop(message_id, None)
            if msg is None:
                return
            if requeue:
                self._queues[msg.queue].append(msg)
                return
            dlq_name = f"dlq.{msg.queue}" if not msg.queue.startswith("dlq.") else msg.queue
            self._declared_queues.add(dlq_name)
            dlq_msg = BrokerMessage(
                message_id=msg.message_id,
                queue=dlq_name,
                payload={
                    **msg.payload,
                    "_dlq_reason": reason,
                    "_original_queue": msg.queue,
                },
                enqueued_at=time.time(),
                expires_at=msg.expires_at,
                attempts=msg.attempts,
                headers={**msg.headers, "dlq_reason": reason},
            )
            self._queues[dlq_name].append(dlq_msg)
            self._counters[msg.queue]["dead_lettered"] += 1

    def peek_dlq(self, dlq_name: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            results: list[dict[str, Any]] = []
            for qname, q in self._queues.items():
                if not qname.startswith("dlq."):
                    continue
                if dlq_name and qname != dlq_name:
                    continue
                for msg in list(q)[-limit:]:
                    results.append(
                        {
                            "queue": qname,
                            "message_id": msg.message_id,
                            "reason": msg.headers.get("dlq_reason")
                            or msg.payload.get("_dlq_reason", "unknown"),
                            "enqueued_at": msg.enqueued_at,
                            "payload": msg.payload,
                        }
                    )
            return results

    def drain_dlq(self, dlq_name: str) -> int:
        with self._lock:
            q = self._queues.get(dlq_name)
            if not q:
                return 0
            count = len(q)
            q.clear()
            return count

    def revoke_matching(self, queue: str, polling_run_id: str) -> bool:
        """Removes a queued task on cancel before worker receipt."""
        with self._lock:
            q = self._queues.get(queue)
            if not q:
                return False
            for idx, msg in enumerate(q):
                if msg.payload.get("polling_run_id") == polling_run_id:
                    del q[idx]
                    return True
            return False

    def is_expired(self, msg: BrokerMessage) -> bool:
        if not msg.expires_at:
            return False
        return utc_now() > parse_iso(msg.expires_at)

    def stats(self) -> list[dict[str, Any]]:
        now = time.time()
        with self._lock:
            all_queues = sorted(self._declared_queues | set(self._queues.keys()))
            output: list[dict[str, Any]] = []
            for qname in all_queues:
                q = self._queues.get(qname)
                depth = len(q) if q else 0
                oldest_age = round(now - q[0].enqueued_at, 2) if q and depth > 0 else 0.0
                counts = self._counters[qname]
                output.append(
                    {
                        "queue": qname,
                        "is_dlq": qname.startswith("dlq."),
                        "depth": depth,
                        "oldest_message_age_seconds": oldest_age,
                        "paused": qname in self._paused,
                        "published": counts["published"],
                        "acked": counts["acked"],
                        "expired": counts["expired"],
                        "dead_lettered": counts["dead_lettered"],
                    }
                )
            return output
