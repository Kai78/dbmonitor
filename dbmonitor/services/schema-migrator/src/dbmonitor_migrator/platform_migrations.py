from __future__ import annotations

from dbmonitor_platform_db.database import PlatformDatabase

PLATFORM_DDL = """
CREATE TABLE IF NOT EXISTS platform_database_servers (
    server_id      TEXT PRIMARY KEY,
    hostname       TEXT NOT NULL,
    address        TEXT NOT NULL,
    port           INTEGER NOT NULL,
    db_type        TEXT NOT NULL,
    environment    TEXT NOT NULL DEFAULT 'production',
    region         TEXT NOT NULL DEFAULT 'eu-west-1',
    network_zone   TEXT NOT NULL DEFAULT 'default',
    tags_json      TEXT NOT NULL DEFAULT '{}',
    ownership      TEXT NOT NULL DEFAULT 'platform-dba',
    secret_ref     TEXT NOT NULL,
    metadata_json  TEXT NOT NULL DEFAULT '{}',
    status         TEXT NOT NULL DEFAULT 'active',
    config_version INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_servers_endpoint
    ON platform_database_servers (hostname, port, db_type);

CREATE TABLE IF NOT EXISTS platform_provider_instances (
    provider_instance_id TEXT PRIMARY KEY,
    name                 TEXT NOT NULL UNIQUE,
    plugin_id            TEXT NOT NULL,
    provider_name        TEXT NOT NULL,
    credentials_ref      TEXT NOT NULL,
    config_json          TEXT NOT NULL DEFAULT '{}',
    interval_seconds     INTEGER NOT NULL DEFAULT 300,
    next_due_at          TEXT NOT NULL,
    lease_owner          TEXT,
    lease_expires_at     TEXT,
    last_run_at          TEXT,
    last_status          TEXT,
    enabled              INTEGER NOT NULL DEFAULT 1,
    created_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS platform_provider_associations (
    association_id       TEXT PRIMARY KEY,
    server_id            TEXT NOT NULL REFERENCES platform_database_servers(server_id),
    provider_instance_id TEXT NOT NULL REFERENCES platform_provider_instances(provider_instance_id),
    provider_resource_id TEXT NOT NULL,
    last_seen_at         TEXT NOT NULL,
    missed_runs          INTEGER NOT NULL DEFAULT 0,
    UNIQUE (provider_instance_id, provider_resource_id)
);

CREATE TABLE IF NOT EXISTS platform_discovery_runs (
    discovery_run_id     TEXT PRIMARY KEY,
    provider_instance_id TEXT NOT NULL,
    provider_name        TEXT NOT NULL,
    plugin_id            TEXT NOT NULL,
    status               TEXT NOT NULL,
    trigger              TEXT NOT NULL,
    requested_by         TEXT,
    dry_run              INTEGER NOT NULL DEFAULT 0,
    discovered_count     INTEGER NOT NULL DEFAULT 0,
    created_count        INTEGER NOT NULL DEFAULT 0,
    updated_count        INTEGER NOT NULL DEFAULT 0,
    error_message        TEXT,
    preview_json         TEXT,
    created_at           TEXT NOT NULL,
    finished_at          TEXT
);

CREATE TABLE IF NOT EXISTS platform_polling_pools (
    name                         TEXT PRIMARY KEY,
    queue_template               TEXT NOT NULL,
    results_queue                TEXT NOT NULL,
    expiry_factor                REAL NOT NULL DEFAULT 1.0,
    celery_pool                  TEXT NOT NULL DEFAULT 'threads',
    emit_started_events          INTEGER NOT NULL DEFAULT 0,
    default_task_timeout_seconds INTEGER NOT NULL DEFAULT 20,
    created_at                   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS platform_polling_profiles (
    name                       TEXT PRIMARY KEY,
    pool                       TEXT NOT NULL REFERENCES platform_polling_pools(name),
    interval_seconds           INTEGER NOT NULL,
    collector_groups_json      TEXT NOT NULL,
    timeout_seconds            INTEGER NOT NULL,
    retry_policy_json          TEXT NOT NULL,
    max_concurrency_per_server INTEGER NOT NULL DEFAULT 1,
    missed_interval_policy     TEXT NOT NULL DEFAULT 'skip',
    freshness_slo_seconds      INTEGER NOT NULL DEFAULT 150,
    created_at                 TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS platform_assignment_rules (
    rule_id            TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    db_type            TEXT,
    environment        TEXT,
    network_zone       TEXT,
    tag_filter_json    TEXT,
    profile_names_json TEXT NOT NULL,
    priority           INTEGER NOT NULL DEFAULT 100,
    enabled            INTEGER NOT NULL DEFAULT 1,
    created_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS platform_server_polling_assignments (
    assignment_id     TEXT PRIMARY KEY,
    server_id         TEXT NOT NULL REFERENCES platform_database_servers(server_id),
    profile_name      TEXT NOT NULL REFERENCES platform_polling_profiles(name),
    source            TEXT NOT NULL DEFAULT 'rule',
    concurrency_group TEXT,
    overrides_json    TEXT NOT NULL DEFAULT '{}',
    enabled           INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT NOT NULL,
    UNIQUE (server_id, profile_name)
);

CREATE TABLE IF NOT EXISTS platform_polling_state (
    assignment_id         TEXT PRIMARY KEY REFERENCES platform_server_polling_assignments(assignment_id),
    server_id             TEXT NOT NULL,
    profile_name          TEXT NOT NULL,
    db_type               TEXT NOT NULL,
    pool                  TEXT NOT NULL,
    enabled               INTEGER NOT NULL DEFAULT 1,
    next_due_at           TEXT NOT NULL,
    lease_owner           TEXT,
    lease_expires_at      TEXT,
    last_run_id           TEXT,
    last_success_at       TEXT,
    consecutive_failures  INTEGER NOT NULL DEFAULT 0,
    missed_interval_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_polling_state_due
    ON platform_polling_state (enabled, next_due_at);

CREATE TABLE IF NOT EXISTS platform_polling_runs (
    polling_run_id   TEXT PRIMARY KEY,
    assignment_id    TEXT,
    server_id        TEXT NOT NULL,
    db_type          TEXT NOT NULL,
    profile_name     TEXT NOT NULL,
    pool             TEXT NOT NULL,
    collector_groups_json TEXT NOT NULL,
    attempt_count    INTEGER NOT NULL DEFAULT 1,
    status           TEXT NOT NULL,
    trigger          TEXT NOT NULL,
    requested_by     TEXT,
    scheduled_for    TEXT NOT NULL,
    expires_at       TEXT,
    started_at       TEXT,
    finished_at      TEXT,
    error_category   TEXT,
    error_message    TEXT,
    collectors_json  TEXT,
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_polling_runs_created
    ON platform_polling_runs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_polling_runs_server
    ON platform_polling_runs (server_id, created_at DESC);

CREATE TABLE IF NOT EXISTS platform_manual_run_requests (
    request_id      TEXT PRIMARY KEY,
    idempotency_key TEXT UNIQUE,
    kind            TEXT NOT NULL,
    scope_json      TEXT NOT NULL,
    requested_by    TEXT NOT NULL,
    dry_run         INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending',
    run_ids_json    TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL,
    processed_at    TEXT
);

CREATE TABLE IF NOT EXISTS platform_outbox (
    outbox_id    TEXT PRIMARY KEY,
    queue_name   TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    expires_at   TEXT,
    created_at   TEXT NOT NULL,
    published_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
    ON platform_outbox (published_at, created_at);

CREATE TABLE IF NOT EXISTS platform_plugin_registry (
    plugin_id              TEXT PRIMARY KEY,
    kind                   TEXT NOT NULL,
    version                TEXT NOT NULL,
    db_type                TEXT,
    provider_name          TEXT,
    schema_version         TEXT,
    collector_groups_json  TEXT NOT NULL DEFAULT '{}',
    enabled_pools_json     TEXT NOT NULL DEFAULT '[]',
    enabled                INTEGER NOT NULL DEFAULT 1,
    drift_detected         INTEGER NOT NULL DEFAULT 0,
    bundle_path            TEXT NOT NULL,
    updated_at             TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS platform_plugin_schema_versions (
    namespace       TEXT PRIMARY KEY,
    plugin_id       TEXT NOT NULL,
    schema_version  TEXT NOT NULL,
    checksums_json  TEXT NOT NULL,
    applied_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS platform_partition_catalog (
    partition_id   TEXT PRIMARY KEY,
    schema_name    TEXT NOT NULL,
    table_name     TEXT NOT NULL,
    partition_name TEXT NOT NULL,
    range_start    TEXT NOT NULL,
    range_end      TEXT NOT NULL,
    retention_days INTEGER NOT NULL,
    created_at     TEXT NOT NULL,
    UNIQUE (schema_name, table_name, partition_name)
);

CREATE TABLE IF NOT EXISTS platform_audit_log (
    audit_id     TEXT PRIMARY KEY,
    actor        TEXT NOT NULL,
    action       TEXT NOT NULL,
    target_type  TEXT NOT NULL,
    target_id    TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL
);
"""


def apply_platform_migrations(db: PlatformDatabase) -> None:
    db.execute_script(PLATFORM_DDL)
