import { useState } from 'react';
import type { AssignmentRule, ProviderInstance, ServerRecord } from '../types';
import { StatusText, formatShortTime } from './StatusText';

interface InventoryViewProps {
  servers: ServerRecord[];
  providers: ProviderInstance[];
  rules: AssignmentRule[];
  onSetFaultMode: (serverId: string, faultMode: string) => Promise<void>;
  onTriggerDiscovery: (providerInstanceId: string | null, dryRun: boolean) => Promise<void>;
  onCreateRule: (payload: Record<string, unknown>) => Promise<void>;
  onCreateAssignment: (payload: Record<string, unknown>) => Promise<void>;
}

const FAULT_MODES = [
  { value: 'none', label: 'Nominal (No Fault)' },
  { value: 'partial_timeout', label: 'Partial Collector Timeout' },
  { value: 'unreachable', label: 'Database Unreachable' },
  { value: 'auth_error', label: 'Authentication Failed (Fail-Fast)' },
  { value: 'bad_schema', label: 'Undeclared Schema Column' },
  { value: 'worker_crash', label: 'Worker Crash (Lease Expiry)' },
  { value: 'schema_ahead', label: 'Schema Ahead (schema_not_ready)' },
];

export function InventoryView({
  servers,
  providers,
  rules,
  onSetFaultMode,
  onTriggerDiscovery,
  onCreateRule,
  onCreateAssignment,
}: InventoryViewProps) {
  const [dbFilter, setDbFilter] = useState<string>('all');
  const [ruleName, setRuleName] = useState('');
  const [ruleDbType, setRuleDbType] = useState('');
  const [ruleEnv, setRuleEnv] = useState('production');
  const [ruleProfiles, setRuleProfiles] = useState('high_frequency');

  const [manualServerId, setManualServerId] = useState('');
  const [manualProfile, setManualProfile] = useState('high_frequency');
  const [feedback, setFeedback] = useState<string | null>(null);

  const filteredServers =
    dbFilter === 'all' ? servers : servers.filter((s) => s.db_type === dbFilter);

  const handleRuleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFeedback(null);
    try {
      await onCreateRule({
        name: ruleName,
        db_type: ruleDbType || null,
        environment: ruleEnv || null,
        profile_names: ruleProfiles
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
      });
      setRuleName('');
      setFeedback('Assignment rule created.');
    } catch (err) {
      setFeedback((err as Error).message);
    }
  };

  const handleManualAssign = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualServerId) return;
    setFeedback(null);
    try {
      await onCreateAssignment({
        server_id: manualServerId,
        profile_name: manualProfile,
      });
      setFeedback('Manual assignment created (protected from rule overwrites).');
    } catch (err) {
      setFeedback((err as Error).message);
    }
  };

  return (
    <div className="space-y-8">
      {feedback && (
        <div className="bg-white border border-slate-300 rounded-lg px-4 py-3 text-xs text-slate-800 flex items-center justify-between">
          <span>{feedback}</span>
          <button onClick={() => setFeedback(null)} className="text-slate-500 hover:text-slate-900">
            Dismiss
          </button>
        </div>
      )}

      {/* Canonical Servers Table */}
      <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900">
              Canonical Database Servers
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Reconciled from discovery providers with config_version tracking and fault simulation
            </p>
          </div>
          <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg">
            {['all', 'postgresql', 'oracle', 'mssql'].map((engine) => (
              <button
                key={engine}
                onClick={() => setDbFilter(engine)}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${
                  dbFilter === engine
                    ? 'bg-white text-slate-900 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                {engine === 'all' ? 'All Engines' : engine}
              </button>
            ))}
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/70 text-xs font-medium text-slate-500">
                <th className="py-2.5 px-4">Hostname &amp; Endpoint</th>
                <th className="py-2.5 px-4">Engine · Env · Region</th>
                <th className="py-2.5 px-4">Providers</th>
                <th className="py-2.5 px-4 text-right">Config Ver</th>
                <th className="py-2.5 px-4">Latest Health</th>
                <th className="py-2.5 px-4">Fault Simulation</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredServers.map((srv) => {
                const currentFault = String(srv.metadata?.fault_mode ?? 'none');
                return (
                  <tr key={srv.server_id} className="hover:bg-slate-50/60">
                    <td className="py-3 px-4">
                      <div className="font-mono text-xs font-medium text-slate-900">
                        {srv.hostname}
                      </div>
                      <div className="font-mono text-xs text-slate-500 mt-0.5">
                        {srv.address}:{srv.port} · {srv.ownership}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-xs text-slate-700">
                      {srv.db_type} <span className="text-slate-400">·</span> {srv.environment}{' '}
                      <span className="text-slate-400">·</span> {srv.region}
                    </td>
                    <td className="py-3 px-4 text-xs text-slate-600">
                      {srv.providers.map((p) => p.provider_instance_name).join(', ') || '—'}
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-xs tabular-nums text-slate-700">
                      v{srv.config_version}
                    </td>
                    <td className="py-3 px-4 text-xs">
                      {srv.latest_health ? (
                        <div>
                          <StatusText
                            status={srv.latest_health.is_available ? 'succeeded' : 'failed'}
                          />
                          <span className="ml-2 font-mono text-slate-500 tabular-nums">
                            {srv.latest_health.response_time_ms ?? '—'} ms
                          </span>
                        </div>
                      ) : (
                        <span className="text-slate-400">Awaiting poll</span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      <select
                        value={currentFault}
                        onChange={(e) => onSetFaultMode(srv.server_id, e.target.value)}
                        aria-label={`Fault mode for ${srv.hostname}`}
                        className="text-xs border border-slate-200 rounded-md px-2.5 py-1.5 bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-teal-600/20"
                      >
                        {FAULT_MODES.map((fm) => (
                          <option key={fm.value} value={fm.value}>
                            {fm.label}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Discovery Provider Instances */}
      <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-900">
              Discovery Provider Instances
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Scheduled &amp; manual discovery via discovery.run and discovery.results
            </p>
          </div>
          <button
            onClick={() => onTriggerDiscovery(null, true)}
            className="px-3.5 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 rounded-md whitespace-nowrap"
          >
            Preview Dry-Run All
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/70 text-xs font-medium text-slate-500">
                <th className="py-2.5 px-4">Instance</th>
                <th className="py-2.5 px-4">Plugin</th>
                <th className="py-2.5 px-4 text-right">Interval</th>
                <th className="py-2.5 px-4">Last Run</th>
                <th className="py-2.5 px-4">Status</th>
                <th className="py-2.5 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {providers.map((p) => (
                <tr key={p.provider_instance_id} className="hover:bg-slate-50/60">
                  <td className="py-2.5 px-4 font-medium text-xs text-slate-900">{p.name}</td>
                  <td className="py-2.5 px-4 font-mono text-xs text-slate-600">{p.plugin_id}</td>
                  <td className="py-2.5 px-4 text-right font-mono text-xs tabular-nums">
                    {p.interval_seconds}s
                  </td>
                  <td className="py-2.5 px-4 font-mono text-xs text-slate-500">
                    {formatShortTime(p.last_run_at)}
                  </td>
                  <td className="py-2.5 px-4">
                    <StatusText status={p.last_status || 'queued'} />
                  </td>
                  <td className="py-2.5 px-4 text-right space-x-2">
                    <button
                      onClick={() => onTriggerDiscovery(p.provider_instance_id, false)}
                      className="px-3 py-1 text-xs font-medium text-teal-800 bg-teal-50 hover:bg-teal-100 border border-teal-200 rounded whitespace-nowrap"
                    >
                      Run Now
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Assignment Rules & Manual Assignments */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className="bg-white border border-slate-200 rounded-lg p-6 space-y-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Assignment Rules</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Inventory evaluates rules on server creation/update; manual assignments are never overwritten
            </p>
          </div>
          <div className="divide-y divide-slate-100 border border-slate-200 rounded-md">
            {rules.map((r) => (
              <div key={r.rule_id} className="px-4 py-2.5 text-xs flex items-center justify-between">
                <div>
                  <div className="font-medium text-slate-900">{r.name}</div>
                  <div className="text-slate-500 font-mono mt-0.5">
                    db_type={r.db_type || '*'} · env={r.environment || '*'} →{' '}
                    {JSON.parse(r.profile_names_json).join(', ')}
                  </div>
                </div>
                <span className="font-mono text-slate-500">p{r.priority}</span>
              </div>
            ))}
          </div>

          <form onSubmit={handleRuleSubmit} className="pt-2 space-y-3 border-t border-slate-200">
            <div className="text-xs font-semibold text-slate-700">Add Assignment Rule</div>
            <div className="grid grid-cols-2 gap-3">
              <input
                type="text"
                required
                placeholder="Rule name"
                value={ruleName}
                onChange={(e) => setRuleName(e.target.value)}
                className="col-span-2 text-xs border border-slate-200 rounded px-3 py-2"
              />
              <input
                type="text"
                placeholder="db_type (optional)"
                value={ruleDbType}
                onChange={(e) => setRuleDbType(e.target.value)}
                className="text-xs border border-slate-200 rounded px-3 py-2"
              />
              <input
                type="text"
                placeholder="environment"
                value={ruleEnv}
                onChange={(e) => setRuleEnv(e.target.value)}
                className="text-xs border border-slate-200 rounded px-3 py-2"
              />
              <input
                type="text"
                placeholder="profiles (comma-separated)"
                value={ruleProfiles}
                onChange={(e) => setRuleProfiles(e.target.value)}
                className="col-span-2 text-xs border border-slate-200 rounded px-3 py-2"
              />
            </div>
            <button
              type="submit"
              className="px-4 py-2 text-xs font-medium text-white bg-slate-900 hover:bg-slate-800 rounded-md"
            >
              Create Rule
            </button>
          </form>
        </section>

        <section className="bg-white border border-slate-200 rounded-lg p-6 space-y-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900">
              Manual Profile Assignment
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Bind a server to an additional profile with source=manual (validates group intersection)
            </p>
          </div>
          <form onSubmit={handleManualAssign} className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Server</label>
              <select
                value={manualServerId}
                onChange={(e) => setManualServerId(e.target.value)}
                className="w-full text-xs border border-slate-200 rounded px-3 py-2 bg-white"
              >
                <option value="">Select server...</option>
                {servers.map((s) => (
                  <option key={s.server_id} value={s.server_id}>
                    {s.hostname} ({s.db_type} · {s.environment})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Profile Name</label>
              <input
                type="text"
                value={manualProfile}
                onChange={(e) => setManualProfile(e.target.value)}
                className="w-full text-xs border border-slate-200 rounded px-3 py-2"
              />
            </div>
            <button
              type="submit"
              className="px-4 py-2 text-xs font-medium text-white bg-teal-700 hover:bg-teal-800 rounded-md"
            >
              Bind Manual Assignment
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
