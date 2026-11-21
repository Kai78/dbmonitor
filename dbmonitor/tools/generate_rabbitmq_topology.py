#!/usr/bin/env python3
"""Generates deploy/rabbitmq/topology.generated.json from pools and enabled db_types."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_POOLS = {
    "high_frequency": {
        "queue_template": "poll.{db_type}.high_frequency",
        "results_queue": "results.high_frequency",
        "expiry_factor": 1.0,
    },
    "low_frequency": {
        "queue_template": "poll.{db_type}.low_frequency",
        "results_queue": "results.low_frequency",
        "expiry_factor": 1.0,
    },
}

DEFAULT_DB_TYPES = ["postgresql", "oracle", "mssql"]


def generate_topology(
    pools: dict[str, dict] | None = None,
    db_types: list[str] | None = None,
) -> dict:
    pools = pools or DEFAULT_POOLS
    db_types = db_types or DEFAULT_DB_TYPES

    queues: list[dict] = [
        {"name": "discovery.run", "type": "quorum", "dlq": "dlq.discovery.run"},
        {"name": "discovery.results", "type": "quorum", "dlq": "dlq.discovery.results"},
    ]

    for pool_name, pool_cfg in pools.items():
        results_q = pool_cfg["results_queue"]
        queues.append({"name": results_q, "type": "quorum", "dlq": f"dlq.{results_q}"})
        for db_type in db_types:
            qname = pool_cfg["queue_template"].format(db_type=db_type, zone="default")
            queues.append(
                {
                    "name": qname,
                    "type": "quorum",
                    "pool": pool_name,
                    "db_type": db_type,
                    "dlq": f"dlq.{qname}",
                }
            )

    dlqs = [{"name": q["dlq"], "type": "quorum", "source_queue": q["name"]} for q in queues]
    return {
        "generated_by": "tools/generate_rabbitmq_topology.py",
        "queues": queues,
        "dead_letter_queues": dlqs,
    }


def write_topology() -> Path:
    dest = ROOT / "deploy" / "rabbitmq" / "topology.generated.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    topo = generate_topology()
    dest.write_text(json.dumps(topo, indent=2) + "\n", encoding="utf-8")
    return dest


if __name__ == "__main__":
    out = write_topology()
    print(f"Generated RabbitMQ topology: {out.relative_to(ROOT)}")
