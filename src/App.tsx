import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  Boxes,
  Database,
  Layers,
  Play,
  RefreshCw,
  Server,
  Workflow,
  X,
} from 'lucide-react';
import { api } from './api';
import { InventoryView } from './components/InventoryView';
import { MetricsReportingView } from './components/MetricsReportingView';
import { OverviewView } from './components/OverviewView';
import { PluginsBundlesView } from './components/PluginsBundlesView';
import { PoolsProfilesView } from './components/PoolsProfilesView';
import { RunsOutboxView } from './components/RunsOutboxView';
import type {
  AssignmentRule,
  DiscoveryRun,
  ManualRunRequest,
  OutboxRow,
  OverviewResponse,
  PluginRegistryItem,
  PluginSchemaVersion,
  PollingPool,
  PollingProfile,
  PollingRun,
  ProviderInstance,
  ServerRecord,
} from './types';

type TabId =
  | 'overview'
  | 'inventory'
  | 'pools'
  | 'runs'
  | 'plugins'
  | 'metrics';

const NAV_ITEMS: Array<{ id: TabId; label: string; icon: typeof Activity }> = [
  { id: 'overview', label: 'Overview', icon: Activity },
  { id: 'inventory', label: 'Inventory & Rules', icon: Server },
  { id: 'pools', label: 'Pools & Profiles', icon: Layers },
  { id: 'runs', label: 'Runs & Outbox', icon: Workflow },
  { id: 'plugins', label: 'Plugins & Bundles', icon: Boxes },
  { id: 'metrics', label: 'Metrics & Reporting', icon: Database },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [loading, setLoading] = useState<boolean>(true);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [actionToast, setActionToast] = useState<string | null>(null);

  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [servers, setServers] = useState<ServerRecord[]>([]);
  const [providers, setProviders] = useState<ProviderInstance[]>([]);
  const [rules, setRules] = useState<AssignmentRule[]>([]);
  const [pools, setPools] = useState<PollingPool[]>([]);
  const [profiles, setProfiles] = useState<PollingProfile[]>([]);
  const [pollingRuns, setPollingRuns] = useState<PollingRun[]>([]);
  const [discoveryRuns, setDiscoveryRuns] = useState<DiscoveryRun[]>([]);
  const [manualRequests, setManualRequests] = useState<ManualRunRequest[]>([]);
  const [outbox, setOutbox] = useState<OutboxRow[]>([]);
  const [dlqMessages, setDlqMessages] = useState<Array<Record<string, unknown>>>([]);
  const [runStatusFilter, setRunStatusFilter] = useState<string>('');
  const [plugins, setPlugins] = useState<PluginRegistryItem[]>([]);
  const [schemaVersions, setSchemaVersions] = useState<PluginSchemaVersion[]>([]);
  const [bundles, setBundles] = useState<
    Record<
      string,
      {
        files: string[];
        schema_manifest?: Record<string, unknown>;
        migrations?: Record<string, string>;
      }
    >
  >({});

  // Manual Poll Modal state
  const [pollModalOpen, setPollModalOpen] = useState(false);
  const [manualScopeType, setManualScopeType] = useState<'all' | 'server' | 'db_type'>('all');
  const [manualServerId, setManualServerId] = useState('');
  const [manualDbType, setManualDbType] = useState('postgresql');
  const [manualProfile, setManualProfile] = useState('high_frequency');
  const [manualIdempotencyKey, setManualIdempotencyKey] = useState('');

  const refreshAll = useCallback(async () => {
    try {
      const [ov, srv, prov, rul, pl, prf, pruns, druns, dlq, plg] = await Promise.all([
        api.getOverview(),
        api.getServers(),
        api.getProviders(),
        api.getRules(),
        api.getPools(),
        api.getProfiles(),
        api.getPollingRuns(runStatusFilter ? { status: runStatusFilter } : undefined),
        api.getDiscoveryRuns(),
        api.getDlq(),
        api.getPlugins(),
      ]);
      setOverview(ov);
      setServers(srv.servers);
      setProviders(prov.providers);
      setRules(rul.rules);
      setPools(pl.pools);
      setProfiles(prf.profiles);
      setPollingRuns(pruns.runs);
      setManualRequests(pruns.manual_requests);
      setOutbox(pruns.outbox);
      setDiscoveryRuns(druns.runs);
      setDlqMessages(dlq.messages);
      setPlugins(plg.plugins);
      setSchemaVersions(plg.schema_versions);
      setBundles(plg.bundles);
      setErrorBanner(null);
    } catch (err) {
      setErrorBanner((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [runStatusFilter]);

  useEffect(() => {
    refreshAll();
    const timer = setInterval(refreshAll, 2500);
    return () => clearInterval(timer);
  }, [refreshAll]);

  const showToast = (msg: string) => {
    setActionToast(msg);
    setTimeout(() => setActionToast(null), 5000);
  };

  const handleRunDiscoveryAll = async () => {
    const res = await api.triggerDiscovery({ dry_run: false, requested_by: 'admin@dbmonitor' });
    showToast(`202 Accepted: Discovery request ${res.request_id.slice(0, 8)} queued for scheduler.`);
    await refreshAll();
  };

  const handleManualPollSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const payload: Record<string, unknown> = {
      profile: manualProfile,
      requested_by: 'admin@dbmonitor',
    };
    if (manualIdempotencyKey.trim()) {
      payload.idempotency_key = manualIdempotencyKey.trim();
    }
    if (manualScopeType === 'server' && manualServerId) {
      payload.server_id = manualServerId;
    } else if (manualScopeType === 'db_type') {
      payload.db_type = manualDbType;
    }
    const res = await api.triggerManualPoll(payload);
    setPollModalOpen(false);
    setManualIdempotencyKey('');
    showToast(`202 Accepted: Manual poll request ${res.request_id.slice(0, 8)} persisted.`);
    await refreshAll();
  };

  const activeNav = NAV_ITEMS.find((n) => n.id === activeTab)!;

  return (
    <div className="min-h-screen flex bg-slate-50 text-slate-900">
      {/* Left Sidebar (248px) */}
      <aside className="w-[248px] shrink-0 bg-white border-r border-slate-200 flex flex-col">
        <div className="h-[60px] px-6 border-b border-slate-200 flex items-center">
          <span className="font-display font-bold text-lg tracking-tight text-slate-900 whitespace-nowrap">
            DBMonitor
          </span>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = item.id === activeTab;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md transition-colors whitespace-nowrap ${
                  active
                    ? 'bg-slate-100 text-slate-900'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                }`}
              >
                <Icon className={`w-4 h-4 shrink-0 ${active ? 'text-teal-700' : 'text-slate-400'}`} />
                <span className="truncate">{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="p-4 border-t border-slate-200">
          <button
            onClick={() => refreshAll()}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 text-xs font-medium text-slate-700 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-md transition-colors whitespace-nowrap"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh State
          </button>
        </div>
      </aside>

      {/* Main Workspace */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Top Bar Contract: Breadcrumb on left, <= 2 primary actions on right */}
        <header className="h-[60px] bg-white border-b border-slate-200 px-8 flex items-center justify-between gap-8 shrink-0">
          <div className="text-sm text-slate-500 whitespace-nowrap truncate">
            <span className="text-slate-400">Platform</span>
            <span className="mx-2 text-slate-300">/</span>
            <span className="font-medium text-slate-900">{activeNav.label}</span>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <button
              onClick={handleRunDiscoveryAll}
              className="px-4 py-2 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-md transition-colors whitespace-nowrap shrink-0"
            >
              Run Discovery
            </button>
            <button
              onClick={() => setPollModalOpen(true)}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium text-white bg-teal-700 hover:bg-teal-800 rounded-md transition-colors whitespace-nowrap shrink-0"
            >
              <Play className="w-3.5 h-3.5" />
              Trigger Manual Poll
            </button>
          </div>
        </header>

        <main className="flex-1 p-8 max-w-[1360px] w-full mx-auto space-y-6">
          {errorBanner && (
            <div className="bg-rose-50 border border-rose-200 rounded-lg px-4 py-3 text-xs text-rose-800">
              {errorBanner}
            </div>
          )}

          {actionToast && (
            <div className="bg-teal-50 border border-teal-200 rounded-lg px-4 py-3 text-xs text-teal-900 flex items-center justify-between">
              <span>{actionToast}</span>
              <button
                onClick={() => setActionToast(null)}
                className="text-teal-700 hover:text-teal-950 font-medium"
              >
                Close
              </button>
            </div>
          )}

          {activeTab === 'overview' && (
            <OverviewView
              data={overview}
              loading={loading}
              onPauseQueue={async (q) => {
                await api.pauseQueue(q);
                showToast(`Paused queue ${q}. Tasks exceeding expires_at will expire without catch-up.`);
                await refreshAll();
              }}
              onResumeQueue={async (q) => {
                await api.resumeQueue(q);
                showToast(`Resumed queue ${q}.`);
                await refreshAll();
              }}
            />
          )}

          {activeTab === 'inventory' && (
            <InventoryView
              servers={servers}
              providers={providers}
              rules={rules}
              onSetFaultMode={async (sid, mode) => {
                await api.setFaultMode(sid, mode);
                showToast(`Updated server fault_mode to '${mode}' (config_version incremented).`);
                await refreshAll();
              }}
              onTriggerDiscovery={async (pid, dryRun) => {
                const res = await api.triggerDiscovery({
                  provider_instance_id: pid,
                  dry_run: dryRun,
                  requested_by: 'admin@dbmonitor',
                });
                showToast(
                  `202 Accepted: ${dryRun ? 'Dry-run' : 'Discovery'} request ${res.request_id.slice(0, 8)} queued.`
                );
                await refreshAll();
              }}
              onCreateRule={async (payload) => {
                await api.createRule(payload);
                await refreshAll();
              }}
              onCreateAssignment={async (payload) => {
                await api.createAssignment(payload);
                await refreshAll();
              }}
            />
          )}

          {activeTab === 'pools' && (
            <PoolsProfilesView
              pools={pools}
              profiles={profiles}
              onCreateProfile={async (payload) => {
                await api.createProfile(payload);
                await refreshAll();
              }}
            />
          )}

          {activeTab === 'runs' && (
            <RunsOutboxView
              pollingRuns={pollingRuns}
              discoveryRuns={discoveryRuns}
              manualRequests={manualRequests}
              outbox={outbox}
              dlqMessages={dlqMessages}
              statusFilter={runStatusFilter}
              onStatusFilterChange={setRunStatusFilter}
              onCancelRun={async (runId) => {
                await api.cancelPollingRun(runId);
                showToast(`Cancelled queued run ${runId.slice(0, 8)}.`);
                await refreshAll();
              }}
              onRetryRun={async (runId) => {
                await api.retryPollingRun(runId);
                showToast(`202 Accepted: Retry requested for run ${runId.slice(0, 8)}.`);
                await refreshAll();
              }}
              onDrainDlq={async (queue) => {
                await api.drainDlq(queue);
                showToast(`Drained ${queue}.`);
                await refreshAll();
              }}
            />
          )}

          {activeTab === 'plugins' && (
            <PluginsBundlesView
              plugins={plugins}
              schemaVersions={schemaVersions}
              bundles={bundles}
              onTogglePlugin={async (pluginId, enabled, enabledPools) => {
                await api.updatePlugin(pluginId, { enabled, enabled_pools: enabledPools });
                showToast(`Updated plugin registry for ${pluginId}.`);
                await refreshAll();
              }}
              onRunCiVerify={() => api.runCiVerify()}
            />
          )}

          {activeTab === 'metrics' && <MetricsReportingView />}
        </main>
      </div>

      {/* Manual Poll Request Modal */}
      {pollModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-lg max-w-md w-full p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-slate-900">
                Manual Polling Run Request
              </h3>
              <button
                onClick={() => setPollModalOpen(false)}
                aria-label="Close modal"
                className="text-slate-400 hover:text-slate-700"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <p className="text-xs text-slate-500">
              Persists a manual_run_requests row and returns 202 Accepted. The scheduler claims and dispatches it through the same outbox and worker path as scheduled work.
            </p>
            <form onSubmit={handleManualPollSubmit} className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Scope</label>
                <select
                  value={manualScopeType}
                  onChange={(e) =>
                    setManualScopeType(e.target.value as 'all' | 'server' | 'db_type')
                  }
                  className="w-full text-xs border border-slate-200 rounded px-3 py-2 bg-white"
                >
                  <option value="all">All Active Servers</option>
                  <option value="db_type">Filter by Database Type</option>
                  <option value="server">Single Server</option>
                </select>
              </div>

              {manualScopeType === 'db_type' && (
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Database Type
                  </label>
                  <select
                    value={manualDbType}
                    onChange={(e) => setManualDbType(e.target.value)}
                    className="w-full text-xs border border-slate-200 rounded px-3 py-2 bg-white"
                  >
                    <option value="postgresql">postgresql</option>
                    <option value="oracle">oracle</option>
                    <option value="mssql">mssql</option>
                  </select>
                </div>
              )}

              {manualScopeType === 'server' && (
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Target Server
                  </label>
                  <select
                    required
                    value={manualServerId}
                    onChange={(e) => setManualServerId(e.target.value)}
                    className="w-full text-xs border border-slate-200 rounded px-3 py-2 bg-white"
                  >
                    <option value="">Select server...</option>
                    {servers.map((s) => (
                      <option key={s.server_id} value={s.server_id}>
                        {s.hostname} ({s.db_type})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Profile</label>
                <select
                  value={manualProfile}
                  onChange={(e) => setManualProfile(e.target.value)}
                  className="w-full text-xs border border-slate-200 rounded px-3 py-2 bg-white"
                >
                  {profiles.map((p) => (
                    <option key={p.name} value={p.name}>
                      {p.name} ({p.pool})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Idempotency Key (optional)
                </label>
                <input
                  type="text"
                  placeholder="e.g. deploy-check-001"
                  value={manualIdempotencyKey}
                  onChange={(e) => setManualIdempotencyKey(e.target.value)}
                  className="w-full text-xs border border-slate-200 rounded px-3 py-2 font-mono"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setPollModalOpen(false)}
                  className="px-4 py-2 text-xs font-medium text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 rounded-md"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 text-xs font-medium text-white bg-teal-700 hover:bg-teal-800 rounded-md"
                >
                  Submit Request (202)
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
