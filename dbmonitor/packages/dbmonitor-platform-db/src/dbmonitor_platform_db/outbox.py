from __future__ import annotations

import json
import sqlite3
from typing import Any

from dbmonitor_common.identifiers import new_uuid, utc_now_iso


def enqueue_outbox(
    conn: sqlite3.Connection,
    queue_name: str,
    payload: dict[str, Any],
    expires_at: str | None = None,
) -> str:
    outbox_id = new_uuid()
    conn.execute(
        """
        INSERT INTO platform_outbox (
            outbox_id, queue_name, payload_json, expires_at, created_at, published_at
        ) VALUES (?, ?, ?, ?, ?, NULL)
        """,
        (outbox_id, queue_name, json.dumps(payload), expires_at, utc_now_iso()),
    )
    return outbox_id
