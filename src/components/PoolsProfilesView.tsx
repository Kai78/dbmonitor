import { useState } from 'react';
import type { PollingPool, PollingProfile } from '../types';

interface PoolsProfilesViewProps {
  pools: PollingPool[];
  profiles: PollingProfile[];
  onCreateProfile: (payload: Record<string, unknown>) => Promise<void>;
}

const ALL_GROUPS = ['health', 'sessions', 'replication', 'performance', 'capacity'];

export function PoolsProfilesView({
  pools,
  profiles,
  onCreateProfile,
}: PoolsProfilesViewProps) {
  const [name, setName] = useState('capacity_daily');
  const [pool, setPool] = useState('low_frequency');
  const [intervalS, setIntervalS] = useState(3600);
  const [timeoutS, setTimeoutS] = useState(120);
  const [selectedGroups, setSelectedGroups] = useState<string[]>(['capacity']);
  const [missedPolicy, setMissedPolicy] = useState<'skip' | 'run_once'>('run_once');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  const toggleGroup = (g: string) => {
    setSelectedGroups((prev) =>
      prev.includes(g) ? prev.filter((item) => item !== g) : [...prev, g]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setOkMsg(null);
    try {
      await onCreateProfile({
        name,
        pool,
        interval_seconds: Number(intervalS),
        timeout_seconds: Number(timeoutS),
        collector_groups: selectedGroups,
        missed_interval_policy: missedPolicy,
      });
      setOkMsg(`Created profile '${name}' on pool '${pool}'. No infrastructure changes required.`);
    } catch (err) {
      setErrorMsg((err as Error).message);
    }
  };

  return (
    <div className="space-y-8">
      {/* Pools */}
      <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200">
          <h2 className="text-base font-semibold text-slate-900">
            Execution Lanes (Polling Pools)
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Queue template poll.&#123;db_type&#125;.&#123;pool&#125; isolates high-frequency health from heavy low-frequency queries
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/70 text-xs font-medium text-slate-500">
                <th className="py-2.5 px-4">Pool</th>
                <th className="py-2.5 px-4">Task Queue Template</th>
                <th className="py-2.5 px-4">Results Queue</th>
                <th className="py-2.5 px-4">Celery Pool</th>
                <th className="py-2.5 px-4 text-right">Expiry Factor</th>
                <th className="py-2.5 px-4 text-right">Default Timeout</th>
                <th className="py-2.5 px-4">Started Events</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {pools.map((p) => (
                <tr key={p.name} className="hover:bg-slate-50/60">
                  <td className="py-2.5 px-4 font-mono text-xs font-semibold text-slate-900">
                    {p.name}
                  </td>
                  <td className="py-2.5 px-4 font-mono text-xs text-slate-700">
                    {p.queue_template}
                  </td>
                  <td className="py-2.5 px-4 font-mono text-xs text-slate-700">
                    {p.results_queue}
                  </td>
                  <td className="py-2.5 px-4 text-xs text-slate-600">{p.celery_pool}</td>
                  <td className="py-2.5 px-4 text-right font-mono text-xs tabular-nums">
                    {p.expiry_factor}x
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono text-xs tabular-nums">
                    {p.default_task_timeout_seconds}s
                  </td>
                  <td className="py-2.5 px-4 text-xs text-slate-600">
                    {p.emit_started_events ? 'Enabled' : 'Disabled'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Profiles & Floor Enforcement */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 items-start">
        <section className="xl:col-span-2 bg-white border border-slate-200 rounded-lg overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200">
            <h2 className="text-base font-semibold text-slate-900">Polling Profiles</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Frequency is data configuration, not plugin identity. Profiles point to an existing pool.
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/70 text-xs font-medium text-slate-500">
                  <th className="py-2.5 px-4">Profile</th>
                  <th className="py-2.5 px-4">Pool</th>
                  <th className="py-2.5 px-4 text-right">Interval</th>
                  <th className="py-2.5 px-4">Collector Groups</th>
                  <th className="py-2.5 px-4">Missed Policy</th>
                  <th className="py-2.5 px-4 text-right">Freshness SLO</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {profiles.map((prof) => (
                  <tr key={prof.name} className="hover:bg-slate-50/60">
                    <td className="py-2.5 px-4 font-mono text-xs font-semibold text-slate-900">
                      {prof.name}
                    </td>
                    <td className="py-2.5 px-4 font-mono text-xs text-slate-600">
                      {prof.pool}
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono text-xs tabular-nums">
                      {prof.interval_seconds}s
                    </td>
                    <td className="py-2.5 px-4 font-mono text-xs text-slate-700">
                      {JSON.parse(prof.collector_groups_json).join(', ')}
                    </td>
                    <td className="py-2.5 px-4 text-xs text-slate-600">
                      {prof.missed_interval_policy}
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono text-xs tabular-nums">
                      {prof.freshness_slo_seconds}s
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="bg-white border border-slate-200 rounded-lg p-6 space-y-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Create Polling Profile</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Enforces platform 30s floor and plugin group min_interval_seconds (e.g. capacity ≥ 600s)
            </p>
          </div>

          {errorMsg && (
            <div className="p-3 bg-rose-50 border border-rose-200 rounded text-xs text-rose-800">
              {errorMsg}
            </div>
          )}
          {okMsg && (
            <div className="p-3 bg-emerald-50 border border-emerald-200 rounded text-xs text-emerald-800">
              {okMsg}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Profile Name</label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full text-xs border border-slate-200 rounded px-3 py-2 font-mono"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Target Pool</label>
                <select
                  value={pool}
                  onChange={(e) => setPool(e.target.value)}
                  className="w-full text-xs border border-slate-200 rounded px-3 py-2 bg-white"
                >
                  {pools.map((p) => (
                    <option key={p.name} value={p.name}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Interval (seconds)
                </label>
                <input
                  type="number"
                  min={1}
                  value={intervalS}
                  onChange={(e) => setIntervalS(Number(e.target.value))}
                  className="w-full text-xs border border-slate-200 rounded px-3 py-2 font-mono tabular-nums"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Timeout (seconds)
                </label>
                <input
                  type="number"
                  min={1}
                  value={timeoutS}
                  onChange={(e) => setTimeoutS(Number(e.target.value))}
                  className="w-full text-xs border border-slate-200 rounded px-3 py-2 font-mono tabular-nums"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Missed Interval Policy
                </label>
                <select
                  value={missedPolicy}
                  onChange={(e) => setMissedPolicy(e.target.value as 'skip' | 'run_once')}
                  className="w-full text-xs border border-slate-200 rounded px-3 py-2 bg-white"
                >
                  <option value="skip">skip (HF)</option>
                  <option value="run_once">run_once (LF)</option>
                </select>
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1.5">
                Collector Groups
              </label>
              <div className="flex flex-wrap gap-2">
                {ALL_GROUPS.map((g) => {
                  const active = selectedGroups.includes(g);
                  return (
                    <button
                      type="button"
                      key={g}
                      onClick={() => toggleGroup(g)}
                      className={`px-2.5 py-1 text-xs font-mono rounded border transition-colors ${
                        active
                          ? 'bg-teal-50 border-teal-300 text-teal-900 font-medium'
                          : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                      }`}
                    >
                      {g}
                    </button>
                  );
                })}
              </div>
            </div>
            <button
              type="submit"
              className="w-full px-4 py-2 text-xs font-medium text-white bg-teal-700 hover:bg-teal-800 rounded-md"
            >
              Validate &amp; Save Profile
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
