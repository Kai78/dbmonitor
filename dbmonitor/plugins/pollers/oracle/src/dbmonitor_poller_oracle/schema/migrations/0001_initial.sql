-- Forward-only migration 0001_initial for metrics_oracle
CREATE SCHEMA IF NOT EXISTS metrics_oracle;

CREATE TABLE IF NOT EXISTS metrics_oracle.instance_health (
    server_id        UUID        NOT NULL,
    polling_run_id   UUID        NOT NULL,
    collected_at     TIMESTAMPTZ NOT NULL,
    is_available     BOOLEAN     NOT NULL,
    response_time_ms INTEGER,
    instance_status  TEXT        NOT NULL,
    open_mode        TEXT        NOT NULL,
    PRIMARY KEY (polling_run_id, collected_at)
) PARTITION BY RANGE (collected_at);

CREATE TABLE IF NOT EXISTS metrics_oracle.active_sessions (
    server_id        UUID        NOT NULL,
    polling_run_id   UUID        NOT NULL,
    collected_at     TIMESTAMPTZ NOT NULL,
    active_sessions  INTEGER     NOT NULL,
    blocked_sessions INTEGER     NOT NULL,
    total_sessions   INTEGER     NOT NULL,
    PRIMARY KEY (polling_run_id, collected_at)
) PARTITION BY RANGE (collected_at);

CREATE TABLE IF NOT EXISTS metrics_oracle.wait_events (
    server_id      UUID        NOT NULL,
    polling_run_id UUID        NOT NULL,
    collected_at   TIMESTAMPTZ NOT NULL,
    wait_class     TEXT        NOT NULL,
    total_waits    BIGINT      NOT NULL,
    time_waited_ms BIGINT      NOT NULL,
    PRIMARY KEY (polling_run_id, collected_at, wait_class)
) PARTITION BY RANGE (collected_at);

CREATE TABLE IF NOT EXISTS metrics_oracle.tablespace_usage (
    server_id       UUID             NOT NULL,
    polling_run_id  UUID             NOT NULL,
    collected_at    TIMESTAMPTZ      NOT NULL,
    tablespace_name TEXT             NOT NULL,
    allocated_bytes BIGINT           NOT NULL,
    used_percent    DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (polling_run_id, collected_at, tablespace_name)
) PARTITION BY RANGE (collected_at);
