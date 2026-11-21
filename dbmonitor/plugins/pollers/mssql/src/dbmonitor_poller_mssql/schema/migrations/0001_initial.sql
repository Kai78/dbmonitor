-- Forward-only migration 0001_initial for metrics_mssql
CREATE SCHEMA IF NOT EXISTS metrics_mssql;

CREATE TABLE IF NOT EXISTS metrics_mssql.instance_health (
    server_id        UUID        NOT NULL,
    polling_run_id   UUID        NOT NULL,
    collected_at     TIMESTAMPTZ NOT NULL,
    is_available     BOOLEAN     NOT NULL,
    response_time_ms INTEGER,
    product_version  TEXT        NOT NULL,
    is_hadr_enabled  BOOLEAN     NOT NULL,
    PRIMARY KEY (polling_run_id, collected_at)
) PARTITION BY RANGE (collected_at);

CREATE TABLE IF NOT EXISTS metrics_mssql.user_connections (
    server_id         UUID        NOT NULL,
    polling_run_id    UUID        NOT NULL,
    collected_at      TIMESTAMPTZ NOT NULL,
    user_connections  INTEGER     NOT NULL,
    blocked_processes INTEGER     NOT NULL,
    PRIMARY KEY (polling_run_id, collected_at)
) PARTITION BY RANGE (collected_at);

CREATE TABLE IF NOT EXISTS metrics_mssql.buffer_pool (
    server_id                    UUID             NOT NULL,
    polling_run_id               UUID             NOT NULL,
    collected_at                 TIMESTAMPTZ      NOT NULL,
    page_life_expectancy_seconds INTEGER          NOT NULL,
    buffer_cache_hit_percent     DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (polling_run_id, collected_at)
) PARTITION BY RANGE (collected_at);

CREATE TABLE IF NOT EXISTS metrics_mssql.database_file_sizes (
    server_id      UUID             NOT NULL,
    polling_run_id UUID             NOT NULL,
    collected_at   TIMESTAMPTZ      NOT NULL,
    database_name  TEXT             NOT NULL,
    file_type      TEXT             NOT NULL,
    size_bytes     BIGINT           NOT NULL,
    used_percent   DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (polling_run_id, collected_at, database_name, file_type)
) PARTITION BY RANGE (collected_at);
