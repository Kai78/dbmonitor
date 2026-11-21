from __future__ import annotations

import json

from dbmonitor_common.identifiers import new_uuid
from dbmonitor_sdk.models.results import CollectorResult, PollResult, ResultEnvelope


def build_result_envelope(
    *,
    polling_run_id: str,
    server_id: str,
    db_type: str,
    plugin_id: str,
    plugin_version: str,
    schema_version: str,
    profile: str,
    pool: str,
    attempt_count: int,
    started_at: str,
    finished_at: str,
    poll_result: PollResult,
    max_result_bytes: int = 1_048_576,
) -> ResultEnvelope:
    status = poll_result.derive_status()
    envelope = ResultEnvelope(
        message_id=new_uuid(),
        polling_run_id=polling_run_id,
        server_id=server_id,
        db_type=db_type,
        plugin_id=plugin_id,
        plugin_version=plugin_version,
        schema_version=schema_version,
        profile=profile,
        pool=pool,
        attempt_count=attempt_count,
        collected_at=poll_result.collected_at,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        collectors=poll_result.collectors,
    )
    # Enforce max_result_bytes by truncating table rows if needed
    raw = json.dumps(envelope.to_dict(), separators=(",", ":")).encode("utf-8")
    if len(raw) > max_result_bytes:
        for col in envelope.collectors:
            for tname, rows in col.tables.items():
                if len(rows) > 10:
                    col.tables[tname] = rows[:10]
                    col.truncated = True
    return envelope


def build_failure_envelope(
    *,
    polling_run_id: str,
    server_id: str,
    db_type: str,
    plugin_id: str,
    plugin_version: str,
    schema_version: str,
    profile: str,
    pool: str,
    attempt_count: int,
    started_at: str,
    finished_at: str,
    error_category: str,
    error_message: str,
) -> ResultEnvelope:
    return ResultEnvelope(
        message_id=new_uuid(),
        polling_run_id=polling_run_id,
        server_id=server_id,
        db_type=db_type,
        plugin_id=plugin_id,
        plugin_version=plugin_version,
        schema_version=schema_version,
        profile=profile,
        pool=pool,
        attempt_count=attempt_count,
        collected_at=finished_at,
        started_at=started_at,
        finished_at=finished_at,
        status="failed",
        collectors=[
            CollectorResult(
                group="health",
                status="failed",
                error_category=error_category,
                error_message=error_message,
                tables={},
            )
        ],
    )
