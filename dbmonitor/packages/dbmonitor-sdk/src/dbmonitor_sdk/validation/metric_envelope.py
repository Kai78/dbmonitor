from __future__ import annotations

import json
from typing import Any

from dbmonitor_sdk.errors import SchemaValidationError

REQUIRED_ENVELOPE_FIELDS = (
    "message_id",
    "polling_run_id",
    "server_id",
    "db_type",
    "plugin_id",
    "plugin_version",
    "schema_version",
    "profile",
    "pool",
    "attempt_count",
    "collected_at",
    "started_at",
    "finished_at",
    "status",
    "collectors",
)


def validate_result_envelope(
    envelope: dict[str, Any],
    max_result_bytes: int = 1_048_576,
) -> None:
    for field_name in REQUIRED_ENVELOPE_FIELDS:
        if field_name not in envelope:
            raise SchemaValidationError(f"Missing result envelope field '{field_name}'.")

    encoded = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
    if len(encoded) > max_result_bytes:
        raise SchemaValidationError(
            f"Result payload size {len(encoded)} bytes exceeds max_result_bytes ({max_result_bytes})."
        )

    if envelope["status"] not in ("succeeded", "partially_succeeded", "failed"):
        raise SchemaValidationError(f"Invalid envelope status '{envelope['status']}'.")
