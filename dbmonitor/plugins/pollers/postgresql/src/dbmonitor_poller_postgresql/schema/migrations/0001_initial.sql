-- Forward-only migration 0001_initial for metrics_postgresql
CREATE SCHEMA IF NOT EXISTS metrics_postgresql;

CREATE TABLE IF NOT EXISTS metrics_postgresql.instance_health (
    server_id        UUID        NOT NULL,
    polling_run_id   UUID        NOT NULL,
    collected_at     TIMESTAMPTZ NOT NULL,
    is_available     BOOLEAN     NOT NULL,
    response_time_ms INTEGER,
    server_version   TEXT,
    in_recovery      BOOLEAN     NOT NULL,
    PRIMARY KEY (polling_run_id, collected_at)
) PARTITION BY RANGE (collected_at);

CREATE INDEX IF NOT EXISTS idx_pg_health_server_time
    ON metrics_postgresql.instance_health (server_id, collected_at DESC);

CREATE TABLE IF NOT EXISTS metrics_postgresql.connections (
    server_id           UUID        NOT NULL,
    polling_run_id      UUID        NOT NULL,
    collected_at        TIMESTAMPTZ NOT NULL,
    active_connections  INTEGER     NOT NULL,
    idle_connections    INTEGER     NOT NULL,
    waiting_connections INTEGER     NOT NULL,
    max_connections     INTEGER     NOT NULL,
    PRIMARY KEY (polling_run_id, collected_at)
) PARTITION BY RANGE (collected_at);

CREATE TABLE IF NOT EXISTS metrics_postgresql.replication_lag (
    server_id       UUID        NOT NULL,
    polling_run_id  UUID        NOT NULL,
    collected_at    TIMESTAMPTZ NOT NULL,
    replica_name    TEXT        NOT NULL,
    lag_bytes       BIGINT      NOT NULL,
    replay_lag_ms   INTEGER     NOT NULL,
    PRIMARY KEY (polling_run_id, collected_at, replica_name)
) PARTITION BY RANGE (collected_at);

CREATE TABLE IF NOT EXISTS metrics_postgresql.table_statistics (
    server_id       UUID        NOT NULL,
    polling_run_id  UUID        NOT NULL,
    collected_at    TIMESTAMPTZ NOT NULL,
    schema_name     TEXT        NOT NULL,
    table_name      TEXT        NOT NULL,
    size_bytes      BIGINT      NOT NULL,
    dead_tuples     BIGINT      NOT NULL,
    PRIMARY KEY (polling_run_id, collected_at, schema_name, table_name)
) PARTITION BY RANGE (collected_at);

CREATE TABLE IF NOT EXISTS metrics_postgresql.database_capacity (
    server_id       UUID        NOT NULL,
    polling_run_id  UUID        NOT NULL,
    collected_at    TIMESTAMPTZ NOT NULL,
    database_name   TEXT        NOT NULL,
    allocated_bytes BIGINT      NOT NULL,
    used_percent    DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (polling_run_id, collected_at, database_name)
) PARTITION BY RANGE (collected_at);
