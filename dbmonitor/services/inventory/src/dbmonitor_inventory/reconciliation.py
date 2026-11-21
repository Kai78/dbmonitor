from __future__ import annotations

import json
from typing import Any

from dbmonitor_common.identifiers import new_uuid, utc_now_iso
from dbmonitor_common.logging import get_logger
from dbmonitor_inventory.rules import evaluate_assignment_rules_for_server
from dbmonitor_platform_db.database import PlatformDatabase

log = get_logger("inventory.reconciliation")

STALE_MISSED_RUN_THRESHOLD = 3


def reconcile_discovery_result(db: PlatformDatabase, payload: dict[str, Any]) -> None:
    run_id = payload["discovery_run_id"]
    provider_instance_id = payload["provider_instance_id"]
    status = payload["status"]
    dry_run = bool(payload.get("dry_run", False))
    servers: list[dict[str, Any]] = payload.get("servers", [])
    finished_at = payload.get("finished_at") or utc_now_iso()

    with db.transaction() as conn:
        if status != "succeeded":
            # Section 5.3: Never delete or disable a server because one discovery run failed.
            conn.execute(
                """
                UPDATE platform_discovery_runs
                SET status = ?, error_message = ?, finished_at = ?
                WHERE discovery_run_id = ?
                """,
                ("failed", payload.get("error_message"), finished_at, run_id),
            )
            conn.execute(
                """
                UPDATE platform_provider_instances
                SET last_run_at = ?, last_status = 'failed', lease_owner = NULL, lease_expires_at = NULL
                WHERE provider_instance_id = ?
                """,
                (finished_at, provider_instance_id),
            )
            log.warning(
                "discovery_run_failed_no_inventory_mutation",
                discovery_run_id=run_id,
                provider_instance_id=provider_instance_id,
            )
            return

        if dry_run:
            conn.execute(
                """
                UPDATE platform_discovery_runs
                SET status = 'succeeded', discovered_count = ?, preview_json = ?, finished_at = ?
                WHERE discovery_run_id = ?
                """,
                (len(servers), json.dumps(servers), finished_at, run_id),
            )
            conn.execute(
                """
                UPDATE platform_provider_instances
                SET lease_owner = NULL, lease_expires_at = NULL
                WHERE provider_instance_id = ?
                """,
                (provider_instance_id,),
            )
            return

        now_iso = utc_now_iso()
        seen_resource_ids: set[str] = set()
        created_count = 0
        updated_count = 0

        for item in servers:
            res_id = item["provider_resource_id"]
            seen_resource_ids.add(res_id)

            assoc = conn.execute(
                """
                SELECT server_id FROM platform_provider_associations
                WHERE provider_instance_id = ? AND provider_resource_id = ?
                """,
                (provider_instance_id, res_id),
            ).fetchone()

            existing_server = None
            if assoc is not None:
                existing_server = conn.execute(
                    "SELECT * FROM platform_database_servers WHERE server_id = ?",
                    (assoc["server_id"],),
                ).fetchone()
            else:
                # Reconcile multi-provider discovery by canonical endpoint (hostname, port, db_type)
                existing_server = conn.execute(
                    """
                    SELECT * FROM platform_database_servers
                    WHERE hostname = ? AND port = ? AND db_type = ?
                    """,
                    (item["hostname"], int(item["port"]), item["db_type"]),
                ).fetchone()

            tags_json = json.dumps(item.get("tags", {}), sort_keys=True)
            metadata_json = json.dumps(item.get("metadata", {}), sort_keys=True)

            if existing_server is None:
                server_id = new_uuid()
                conn.execute(
                    """
                    INSERT INTO platform_database_servers (
                        server_id, hostname, address, port, db_type,
                        environment, region, network_zone, tags_json,
                        ownership, secret_ref, metadata_json, status,
                        config_version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 1, ?, ?)
                    """,
                    (
                        server_id,
                        item["hostname"],
                        item["address"],
                        int(item["port"]),
                        item["db_type"],
                        item.get("environment", "production"),
                        item.get("region", "eu-west-1"),
                        item.get("network_zone", "default"),
                        tags_json,
                        item.get("ownership", "platform-dba"),
                        item.get("secret_ref", ""),
                        metadata_json,
                        now_iso,
                        now_iso,
                    ),
                )
                created_count += 1
            else:
                server_id = existing_server["server_id"]
                changed = (
                    existing_server["address"] != item["address"]
                    or existing_server["environment"] != item.get("environment", "production")
                    or existing_server["network_zone"] != item.get("network_zone", "default")
                    or existing_server["secret_ref"] != item.get("secret_ref", "")
                    or existing_server["tags_json"] != tags_json
                    or existing_server["status"] != "active"
                )
                if changed:
                    conn.execute(
                        """
                        UPDATE platform_database_servers
                        SET address = ?, environment = ?, region = ?, network_zone = ?,
                            tags_json = ?, ownership = ?, secret_ref = ?,
                            status = 'active', config_version = config_version + 1, updated_at = ?
                        WHERE server_id = ?
                        """,
                        (
                            item["address"],
                            item.get("environment", "production"),
                            item.get("region", "eu-west-1"),
                            item.get("network_zone", "default"),
                            tags_json,
                            item.get("ownership", "platform-dba"),
                            item.get("secret_ref", ""),
                            now_iso,
                            server_id,
                        ),
                    )
                    updated_count += 1

            conn.execute(
                """
                INSERT INTO platform_provider_associations (
                    association_id, server_id, provider_instance_id,
                    provider_resource_id, last_seen_at, missed_runs
                ) VALUES (?, ?, ?, ?, ?, 0)
                ON CONFLICT(provider_instance_id, provider_resource_id) DO UPDATE SET
                    last_seen_at = excluded.last_seen_at,
                    missed_runs = 0
                """,
                (new_uuid(), server_id, provider_instance_id, res_id, now_iso),
            )

            server_row = conn.execute(
                "SELECT * FROM platform_database_servers WHERE server_id = ?",
                (server_id,),
            ).fetchone()
            evaluate_assignment_rules_for_server(conn, server_row)

        # Apply explicit stale-resource policy (not seen for N successful runs)
        assocs = conn.execute(
            "SELECT * FROM platform_provider_associations WHERE provider_instance_id = ?",
            (provider_instance_id,),
        ).fetchall()
        for a in assocs:
            if a["provider_resource_id"] not in seen_resource_ids:
                new_missed = int(a["missed_runs"]) + 1
                conn.execute(
                    "UPDATE platform_provider_associations SET missed_runs = ? WHERE association_id = ?",
                    (new_missed, a["association_id"]),
                )
                if new_missed >= STALE_MISSED_RUN_THRESHOLD:
                    # Only retire if no other provider association is still fresh
                    fresh_other = conn.execute(
                        """
                        SELECT COUNT(*) FROM platform_provider_associations
                        WHERE server_id = ? AND missed_runs < ?
                        """,
                        (a["server_id"], STALE_MISSED_RUN_THRESHOLD),
                    ).fetchone()[0]
                    if fresh_other == 0:
                        conn.execute(
                            "UPDATE platform_database_servers SET status = 'retired', updated_at = ? WHERE server_id = ?",
                            (now_iso, a["server_id"]),
                        )

        conn.execute(
            """
            UPDATE platform_discovery_runs
            SET status = 'succeeded', discovered_count = ?, created_count = ?,
                updated_count = ?, finished_at = ?
            WHERE discovery_run_id = ?
            """,
            (len(servers), created_count, updated_count, finished_at, run_id),
        )
        conn.execute(
            """
            UPDATE platform_provider_instances
            SET last_run_at = ?, last_status = 'succeeded', lease_owner = NULL, lease_expires_at = NULL
            WHERE provider_instance_id = ?
            """,
            (finished_at, provider_instance_id),
        )
        log.info(
            "discovery_reconciled",
            discovery_run_id=run_id,
            discovered=len(servers),
            created=created_count,
            updated=updated_count,
        )
