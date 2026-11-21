async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data as { error?: string }).error || `Request failed (${res.status})`);
  }
  return data as T;
}

export const api = {
  getOverview: () => request<import('./types').OverviewResponse>('/api/overview'),
  getServers: () => request<{ servers: import('./types').ServerRecord[] }>('/api/servers'),
  setFaultMode: (serverId: string, faultMode: string) =>
    request<{ server_id: string; fault_mode: string }>(`/api/servers/${serverId}/fault-mode`, {
      method: 'POST',
      body: JSON.stringify({ fault_mode: faultMode }),
    }),
  getProviders: () => request<{ providers: import('./types').ProviderInstance[] }>('/api/providers'),
  createProvider: (payload: Record<string, unknown>) =>
    request('/api/providers', { method: 'POST', body: JSON.stringify(payload) }),
  getRules: () => request<{ rules: import('./types').AssignmentRule[] }>('/api/rules'),
  createRule: (payload: Record<string, unknown>) =>
    request('/api/rules', { method: 'POST', body: JSON.stringify(payload) }),
  getAssignments: () => request<{ assignments: Array<Record<string, unknown>> }>('/api/assignments'),
  createAssignment: (payload: Record<string, unknown>) =>
    request('/api/assignments', { method: 'POST', body: JSON.stringify(payload) }),
  toggleAssignment: (assignmentId: string, enabled: boolean) =>
    request(`/api/assignments/${assignmentId}`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled }),
    }),
  getPools: () =>
    request<{ pools: import('./types').PollingPool[]; queues: import('./types').QueueStat[] }>('/api/pools'),
  getProfiles: () => request<{ profiles: import('./types').PollingProfile[] }>('/api/profiles'),
  createProfile: (payload: Record<string, unknown>) =>
    request('/api/profiles', { method: 'POST', body: JSON.stringify(payload) }),
  triggerManualPoll: (payload: Record<string, unknown>) =>
    request<{ request_id: string; status: string }>('/api/polling-runs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getPollingRuns: (params?: { status?: string; pool?: string; db_type?: string }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.pool) qs.set('pool', params.pool);
    if (params?.db_type) qs.set('db_type', params.db_type);
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return request<{
      runs: import('./types').PollingRun[];
      manual_requests: import('./types').ManualRunRequest[];
      outbox: import('./types').OutboxRow[];
    }>(`/api/polling-runs${suffix}`);
  },
  cancelPollingRun: (runId: string) =>
    request(`/api/polling-runs/${runId}/cancel`, { method: 'POST', body: JSON.stringify({}) }),
  retryPollingRun: (runId: string) =>
    request(`/api/polling-runs/${runId}/retry`, { method: 'POST', body: JSON.stringify({}) }),
  triggerDiscovery: (payload: Record<string, unknown>) =>
    request<{ request_id: string; status: string }>('/api/discovery-runs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getDiscoveryRuns: () => request<{ runs: import('./types').DiscoveryRun[] }>('/api/discovery-runs'),
  pauseQueue: (queueName: string) =>
    request(`/api/queues/${encodeURIComponent(queueName)}/pause`, { method: 'POST', body: '{}' }),
  resumeQueue: (queueName: string) =>
    request(`/api/queues/${encodeURIComponent(queueName)}/resume`, { method: 'POST', body: '{}' }),
  getDlq: () => request<{ messages: Array<Record<string, unknown>> }>('/api/dlq'),
  drainDlq: (dlqName: string) =>
    request(`/api/dlq/${encodeURIComponent(dlqName)}/drain`, { method: 'POST', body: '{}' }),
  getPlugins: () =>
    request<{
      plugins: import('./types').PluginRegistryItem[];
      schema_versions: import('./types').PluginSchemaVersion[];
      bundles: Record<
        string,
        {
          files: string[];
          schema_manifest?: Record<string, unknown>;
          migrations?: Record<string, string>;
        }
      >;
    }>('/api/plugins'),
  updatePlugin: (pluginId: string, payload: Record<string, unknown>) =>
    request(`/api/plugins/${pluginId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  runCiVerify: () => request<import('./types').CIReport>('/api/ci/verify', { method: 'POST', body: '{}' }),
  getReportingHealth: () =>
    request<{
      rows: Array<{
        db_type: string;
        server_id: string;
        hostname: string;
        environment: string;
        polling_run_id: string;
        collected_at: string;
        is_available: number;
        response_time_ms: number | null;
      }>;
    }>('/api/reporting/health'),
  getMetricTable: (dbType: string, tableName: string) =>
    request<{
      table: string;
      rows: Array<Record<string, unknown>>;
      partitions: Array<Record<string, unknown>>;
    }>(`/api/metrics/${dbType}/${tableName}`),
  runMaintenance: () =>
    request<{ created_partitions: number; pruned_outbox: number }>('/api/maintenance/run', {
      method: 'POST',
      body: '{}',
    }),
};
