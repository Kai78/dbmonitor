export interface QueueStat {
  queue: string;
  is_dlq: boolean;
  depth: number;
  oldest_message_age_seconds: number;
  paused: boolean;
  published: number;
  acked: number;
  expired: number;
  dead_lettered: number;
}

export interface WorkerStatus {
  worker_id: string;
  db_type: string;
  pool: string;
  queue: string;
  plugin_id: string;
  plugin_version: string;
  processed_count: number;
  expired_count: number;
  connections: {
    active_cached: number;
    cache_hits: number;
    cache_misses: number;
  };
  target_cache: {
    hits: number;
    misses: number;
  };
  secret_cache: {
    hits: number;
    misses: number;
  };
}

export interface ProcessorStatus {
  pool: string;
  queue: string;
  processed_count: number;
  rejected_count: number;
  schema_not_ready_count: number;
}

export interface FreshnessItem {
  assignment_id: string;
  server_id: string;
  hostname: string;
  db_type: string;
  profile_name: string;
  pool: string;
  last_success_at: string | null;
  consecutive_failures: number;
  missed_interval_count: number;
  interval_seconds: number;
  freshness_slo_seconds: number;
  staleness_seconds: number | null;
  slo_compliant: boolean;
}

export interface OverviewResponse {
  summary: {
    active_servers: number;
    active_assignments: number;
    outbox_pending: number;
    dlq_depth: number;
    slo_breaches: number;
    runs_by_status: Record<string, number>;
  };
  freshness: FreshnessItem[];
  queues: QueueStat[];
  workers: WorkerStatus[];
  processors: ProcessorStatus[];
}

export interface ServerRecord {
  server_id: string;
  hostname: string;
  address: string;
  port: number;
  db_type: string;
  environment: string;
  region: string;
  network_zone: string;
  ownership: string;
  secret_ref: string;
  status: string;
  config_version: number;
  tags: Record<string, string>;
  metadata: Record<string, unknown>;
  providers: Array<{
    provider_instance_name: string;
    provider_resource_id: string;
    last_seen_at: string;
    missed_runs: number;
  }>;
  polling_states: Array<{
    assignment_id: string;
    profile_name: string;
    pool: string;
    next_due_at: string;
    last_success_at: string | null;
    consecutive_failures: number;
    missed_interval_count: number;
  }>;
  latest_health: {
    is_available: number;
    response_time_ms: number | null;
    collected_at: string;
  } | null;
}

export interface ProviderInstance {
  provider_instance_id: string;
  name: string;
  plugin_id: string;
  provider_name: string;
  credentials_ref: string;
  config_json: string;
  interval_seconds: number;
  next_due_at: string;
  last_run_at: string | null;
  last_status: string | null;
  enabled: number;
}

export interface AssignmentRule {
  rule_id: string;
  name: string;
  db_type: string | null;
  environment: string | null;
  network_zone: string | null;
  tag_filter_json: string | null;
  profile_names_json: string;
  priority: number;
  enabled: number;
}

export interface PollingPool {
  name: string;
  queue_template: string;
  results_queue: string;
  expiry_factor: number;
  celery_pool: string;
  emit_started_events: number;
  default_task_timeout_seconds: number;
}

export interface PollingProfile {
  name: string;
  pool: string;
  interval_seconds: number;
  collector_groups_json: string;
  timeout_seconds: number;
  retry_policy_json: string;
  max_concurrency_per_server: number;
  missed_interval_policy: string;
  freshness_slo_seconds: number;
}

export interface PollingRun {
  polling_run_id: string;
  assignment_id: string | null;
  server_id: string;
  hostname?: string;
  db_type: string;
  profile_name: string;
  pool: string;
  collector_groups_json: string;
  attempt_count: number;
  status: string;
  trigger: string;
  requested_by: string | null;
  scheduled_for: string;
  expires_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  error_category: string | null;
  error_message: string | null;
  collectors_json: string | null;
  created_at: string;
}

export interface DiscoveryRun {
  discovery_run_id: string;
  provider_instance_id: string;
  provider_name: string;
  plugin_id: string;
  status: string;
  trigger: string;
  requested_by: string | null;
  dry_run: number;
  discovered_count: number;
  created_count: number;
  updated_count: number;
  error_message: string | null;
  preview_json: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface ManualRunRequest {
  request_id: string;
  idempotency_key: string | null;
  kind: string;
  scope_json: string;
  requested_by: string;
  dry_run: number;
  status: string;
  run_ids_json: string;
  created_at: string;
  processed_at: string | null;
}

export interface OutboxRow {
  outbox_id: string;
  queue_name: string;
  payload_json: string;
  expires_at: string | null;
  created_at: string;
  published_at: string | null;
}

export interface PluginRegistryItem {
  plugin_id: string;
  kind: string;
  version: string;
  db_type: string | null;
  provider_name: string | null;
  schema_version: string | null;
  collector_groups_json: string;
  enabled_pools_json: string;
  enabled: number;
  drift_detected: number;
  bundle_path: string;
  updated_at: string;
}

export interface PluginSchemaVersion {
  namespace: string;
  plugin_id: string;
  schema_version: string;
  checksums_json: string;
  applied_at: string;
}

export interface CIReport {
  import_boundaries: {
    passed: boolean;
    checked_files: number;
    violations: string[];
  };
  contract_tests: Array<{
    plugin_id: string;
    kind: string;
    db_type?: string;
    passed: boolean;
    checks: string[];
  }>;
  all_passed: boolean;
}
