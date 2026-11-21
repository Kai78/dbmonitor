from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import timedelta

from dbmonitor_common.identifiers import new_uuid, utc_now, utc_now_iso
from dbmonitor_sdk.contracts.manifest import CollectorGroupSpec, PluginManifest
from dbmonitor_sdk.models.profile import PollingProfile, RetryPolicy
from dbmonitor_sdk.validation.profile_rules import validate_profile_against_plugin


def _load_plugin_manifest_from_registry(
    conn: sqlite3.Connection, db_type: str
) -> PluginManifest | None:
    row = conn.execute(
        """
        SELECT plugin_id, version, db_type, schema_version, collector_groups_json, enabled_pools_json
        FROM platform_plugin_registry
        WHERE kind = 'poller' AND db_type = ? AND enabled = 1
        """,
        (db_type,),
    ).fetchone()
    if row is None:
        return None
    raw_groups = json.loads(row["collector_groups_json"] or "{}")
    groups = {
        gname: CollectorGroupSpec(
            min_interval_seconds=int(gspec["min_interval_seconds"]),
            default_timeout_seconds=int(gspec["default_timeout_seconds"]),
        )
        for gname, gspec in raw_groups.items()
    }
    return PluginManifest(
        plugin_id=row["plugin_id"],
        kind="poller",
        version=row["version"],
        sdk_range=">=1.0,<2.0",
        db_type=row["db_type"],
        schema_version=row["schema_version"],
        collector_groups=groups,
        default_pools=tuple(json.loads(row["enabled_pools_json"] or "[]")),
    )


def create_assignment_if_valid(
    conn: sqlite3.Connection,
    *,
    server_id: str,
    db_type: str,
    profile_name: str,
    source: str = "rule",
    concurrency_group: str | None = None,
) -> bool:
    existing = conn.execute(
        """
        SELECT assignment_id, source FROM platform_server_polling_assignments
        WHERE server_id = ? AND profile_name = ?
        """,
        (server_id, profile_name),
    ).fetchone()

    # Section 5.3: Assignments created manually (source='manual') are never overwritten by rules.
    if existing is not None:
        if source == "rule" and existing["source"] == "manual":
            return False
        return False

    profile_row = conn.execute(
        "SELECT * FROM platform_polling_profiles WHERE name = ?",
        (profile_name,),
    ).fetchone()
    if profile_row is None:
        return False

    manifest = _load_plugin_manifest_from_registry(conn, db_type)
    if manifest is None:
        return False

    retry_raw = json.loads(profile_row["retry_policy_json"])
    profile = PollingProfile(
        name=profile_row["name"],
        pool=profile_row["pool"],
        interval_seconds=int(profile_row["interval_seconds"]),
        collector_groups=tuple(json.loads(profile_row["collector_groups_json"])),
        timeout_seconds=int(profile_row["timeout_seconds"]),
        retry=RetryPolicy(
            max_attempts=int(retry_raw.get("max_attempts", 1)),
            backoff=retry_raw.get("backoff", "none"),
            jitter=bool(retry_raw.get("jitter", False)),
        ),
        max_concurrency_per_server=int(profile_row["max_concurrency_per_server"]),
        missed_interval_policy=profile_row["missed_interval_policy"],
        freshness_slo_seconds=int(profile_row["freshness_slo_seconds"]),
    )

    # Validate non-empty collector-group intersection & interval floor
    validate_profile_against_plugin(profile, manifest)

    now = utc_now()
    # Deterministic small initial jitter (0..3s) so newly discovered servers get polled promptly without aligning
    jitter_s = int(hashlib.md5(f"{server_id}:{profile_name}".encode()).hexdigest()[:4], 16) % 4
    first_due = (now + timedelta(seconds=jitter_s)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    assignment_id = new_uuid()
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    conn.execute(
        """
        INSERT INTO platform_server_polling_assignments (
            assignment_id, server_id, profile_name, source,
            concurrency_group, overrides_json, enabled, created_at
        ) VALUES (?, ?, ?, ?, ?, '{}', 1, ?)
        """,
        (assignment_id, server_id, profile_name, source, concurrency_group, now_iso),
    )
    conn.execute(
        """
        INSERT INTO platform_polling_state (
            assignment_id, server_id, profile_name, db_type, pool,
            enabled, next_due_at, lease_owner, lease_expires_at,
            last_run_id, last_success_at, consecutive_failures, missed_interval_count
        ) VALUES (?, ?, ?, ?, ?, 1, ?, NULL, NULL, NULL, NULL, 0, 0)
        """,
        (assignment_id, server_id, profile_name, db_type, profile.pool, first_due),
    )
    return True


def evaluate_assignment_rules_for_server(
    conn: sqlite3.Connection,
    server_row: sqlite3.Row,
) -> int:
    rules = conn.execute(
        "SELECT * FROM platform_assignment_rules WHERE enabled = 1 ORDER BY priority ASC"
    ).fetchall()
    server_tags = json.loads(server_row["tags_json"] or "{}")
    created = 0

    for rule in rules:
        if rule["db_type"] and rule["db_type"] != server_row["db_type"]:
            continue
        if rule["environment"] and rule["environment"] != server_row["environment"]:
            continue
        if rule["network_zone"] and rule["network_zone"] != server_row["network_zone"]:
            continue
        if rule["tag_filter_json"]:
            tag_filter = json.loads(rule["tag_filter_json"])
            if not all(server_tags.get(k) == v for k, v in tag_filter.items()):
                continue

        for profile_name in json.loads(rule["profile_names_json"]):
            try:
                if create_assignment_if_valid(
                    conn,
                    server_id=server_row["server_id"],
                    db_type=server_row["db_type"],
                    profile_name=profile_name,
                    source="rule",
                ):
                    created += 1
            except ValueError:
                continue
    return created
