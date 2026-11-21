from __future__ import annotations

import json
from typing import Any

from dbmonitor_common.identifiers import new_uuid, utc_now_iso
from dbmonitor_platform_db.database import PlatformDatabase


def seed_platform_defaults(db: PlatformDatabase) -> None:
    now = utc_now_iso()
    with db.transaction() as conn:
        # 1. Default pools
        pools = [
            (
                "high_frequency",
                "poll.{db_type}.high_frequency",
                "results.high_frequency",
                1.0,
                "threads",
                0,
                20,
            ),
            (
                "low_frequency",
                "poll.{db_type}.low_frequency",
                "results.low_frequency",
                1.0,
                "prefork",
                1,
                120,
            ),
        ]
        for name, q_tpl, res_q, exp_f, c_pool, emit_started, timeout_s in pools:
            conn.execute(
                """
                INSERT OR IGNORE INTO platform_polling_pools (
                    name, queue_template, results_queue, expiry_factor,
                    celery_pool, emit_started_events, default_task_timeout_seconds, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (name, q_tpl, res_q, exp_f, c_pool, emit_started, timeout_s, now),
            )

        # 2. Default profiles
        profiles = [
            (
                "high_frequency",
                "high_frequency",
                60,
                json.dumps(["health", "sessions", "replication"]),
                20,
                json.dumps({"max_attempts": 1, "backoff": "none", "jitter": False}),
                1,
                "skip",
                150,
            ),
            (
                "low_frequency",
                "low_frequency",
                900,
                json.dumps(["performance", "capacity"]),
                120,
                json.dumps({"max_attempts": 3, "backoff": "exponential", "jitter": True}),
                1,
                "run_once",
                2700,
            ),
        ]
        for (
            name,
            pool,
            interval_s,
            groups_json,
            timeout_s,
            retry_json,
            max_conc,
            missed_pol,
            slo_s,
        ) in profiles:
            conn.execute(
                """
                INSERT OR IGNORE INTO platform_polling_profiles (
                    name, pool, interval_seconds, collector_groups_json, timeout_seconds,
                    retry_policy_json, max_concurrency_per_server, missed_interval_policy,
                    freshness_slo_seconds, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    pool,
                    interval_s,
                    groups_json,
                    timeout_s,
                    retry_json,
                    max_conc,
                    missed_pol,
                    slo_s,
                    now,
                ),
            )

        # 3. Default provider instances (only seed if empty)
        existing_providers = conn.execute(
            "SELECT COUNT(*) FROM platform_provider_instances"
        ).fetchone()[0]
        if existing_providers == 0:
            providers = [
                (
                    new_uuid(),
                    "cmdb-enterprise",
                    "dbmonitor-provider-cmdb",
                    "cmdb",
                    "secret://vault/providers/cmdb-api-token",
                    json.dumps({}),
                    300,
                    now,
                    1,
                ),
                (
                    new_uuid(),
                    "cloud-prod-eu",
                    "dbmonitor-provider-cloud",
                    "cloud",
                    "secret://aws-sm/providers/cloud-prod",
                    json.dumps({"account": "prod"}),
                    300,
                    now,
                    1,
                ),
                (
                    new_uuid(),
                    "cloud-staging-eu",
                    "dbmonitor-provider-cloud",
                    "cloud",
                    "secret://aws-sm/providers/cloud-staging",
                    json.dumps({"account": "staging"}),
                    600,
                    now,
                    1,
                ),
            ]
            for (
                pid,
                name,
                plugin_id,
                provider_name,
                cred_ref,
                cfg_json,
                interval_s,
                due_at,
                enabled,
            ) in providers:
                conn.execute(
                    """
                    INSERT INTO platform_provider_instances (
                        provider_instance_id, name, plugin_id, provider_name,
                        credentials_ref, config_json, interval_seconds,
                        next_due_at, enabled, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pid,
                        name,
                        plugin_id,
                        provider_name,
                        cred_ref,
                        cfg_json,
                        interval_s,
                        due_at,
                        enabled,
                        now,
                    ),
                )

        # 4. Default assignment rules (only seed if empty)
        existing_rules = conn.execute(
            "SELECT COUNT(*) FROM platform_assignment_rules"
        ).fetchone()[0]
        if existing_rules == 0:
            rules: list[tuple[Any, ...]] = [
                (
                    new_uuid(),
                    "Production PostgreSQL Full Monitoring",
                    "postgresql",
                    "production",
                    None,
                    None,
                    json.dumps(["high_frequency", "low_frequency"]),
                    10,
                    1,
                ),
                (
                    new_uuid(),
                    "Production Oracle Full Monitoring",
                    "oracle",
                    "production",
                    None,
                    None,
                    json.dumps(["high_frequency", "low_frequency"]),
                    10,
                    1,
                ),
                (
                    new_uuid(),
                    "Production MSSQL Full Monitoring",
                    "mssql",
                    "production",
                    None,
                    None,
                    json.dumps(["high_frequency", "low_frequency"]),
                    10,
                    1,
                ),
                (
                    new_uuid(),
                    "Staging Inventory & Capacity Only",
                    None,
                    "staging",
                    None,
                    None,
                    json.dumps(["low_frequency"]),
                    20,
                    1,
                ),
            ]
            for (
                rid,
                name,
                db_type,
                env,
                zone,
                tags_json,
                profiles_json,
                priority,
                enabled,
            ) in rules:
                conn.execute(
                    """
                    INSERT INTO platform_assignment_rules (
                        rule_id, name, db_type, environment, network_zone,
                        tag_filter_json, profile_names_json, priority, enabled, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rid,
                        name,
                        db_type,
                        env,
                        zone,
                        tags_json,
                        profiles_json,
                        priority,
                        enabled,
                        now,
                    ),
                )
