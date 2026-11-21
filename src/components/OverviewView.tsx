import { Pause, Play } from 'lucide-react';
import type { OverviewResponse } from '../types';
import { StatusText, formatShortTime } from './StatusText';

interface OverviewViewProps {
  data: OverviewResponse | null;
  loading: boolean;
  onPauseQueue: (queue: string) => void;
  onResumeQueue: (queue: string) => void;
}

export function OverviewView({
  data,
  loading,
  onPauseQueue,
  onResumeQueue,
}: OverviewViewProps) {
  if (loading && !data) {
    return (
      <div className="space-y-6">
        <div className="h-24 bg-white border border-slate-200 rounded-lg animate-pulse" />
        <div className="h-64 bg-white border border-slate-200 rounded-lg animate-pulse" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="bg-white border border-slate-200 rounded-lg p-8 text-sm text-slate-600">
        Connecting to Python DBMonitor control plane...
      </div>
    );
  }

  const { summary, freshness, queues, workers, processors } = data;
  const activeQueues = queues.filter((q) => !q.is_dlq);

  return (
    <div className="space-y-8">
      {/* KPI Summary Strip */}
      <section className="bg-white border border-slate-200 rounded-lg grid grid-cols-2 md:grid-cols-5 divide-y md:divide-y-0 md:divide-x divide-slate-200">
        <div className="p-5">
          <div className="text-xs font-medium text-slate-500">Active Servers</div>
          <div className="mt-1.5 text-2xl font-semibold font-display tabular-nums text-slate-900">
            {summary.active_servers}
          </div>
          <div className="mt-1 text-xs text-slate-500">Reconciled inventory</div>
        </div>
        <div className="p-5">
          <div className="text-xs font-medium text-slate-500">Polling Assignments</div>
          <div className="mt-1.5 text-2xl font-semibold font-display tabular-nums text-slate-900">
            {summary.active_assignments}
          </div>
          <div className="mt-1 text-xs text-slate-500">HF &amp; LF schedules</div>
        </div>
        <div className="p-5">
          <div className="text-xs font-medium text-slate-500">Unpublished Outbox</div>
          <div className="mt-1.5 text-2xl font-semibold font-display tabular-nums text-slate-900">
            {summary.outbox_pending}
          </div>
          <div className="mt-1 text-xs text-slate-500">Transactional relay lag</div>
        </div>
        <div className="p-5">
          <div className="text-xs font-medium text-slate-500">Dead-Letter Depth</div>
          <div
            className={`mt-1.5 text-2xl font-semibold font-display tabular-nums ${
              summary.dlq_depth > 0 ? 'text-rose-700' : 'text-slate-900'
            }`}
          >
            {summary.dlq_depth}
          </div>
          <div className="mt-1 text-xs text-slate-500">Across dlq.* queues</div>
        </div>
        <div className="p-5">
          <div className="text-xs font-medium text-slate-500">Freshness Breaches</div>
          <div
            className={`mt-1.5 text-2xl font-semibold font-display tabular-nums ${
              summary.slo_breaches > 0 ? 'text-amber-700' : 'text-emerald-700'
            }`}
          >
            {summary.slo_breaches}
          </div>
          <div className="mt-1 text-xs text-slate-500">Against profile SLO</div>
        </div>
      </section>

      {/* Freshness SLO Compliance */}
      <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-900">
              Freshness Service-Level Objectives
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Staleness computed from polling_state.last_success_at per server and profile
            </p>
          </div>
          <div className="text-xs text-slate-500 font-mono tabular-nums">
            {freshness.length} active assignments
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/70 text-xs font-medium text-slate-500">
                <th className="py-2.5 px-4">Server</th>
                <th className="py-2.5 px-4">Engine / Pool</th>
                <th className="py-2.5 px-4">Profile</th>
                <th className="py-2.5 px-4 text-right">Interval</th>
                <th className="py-2.5 px-4 text-right">Staleness / SLO</th>
                <th className="py-2.5 px-4 text-right">Missed</th>
                <th className="py-2.5 px-4">Last Success</th>
                <th className="py-2.5 px-4">SLO State</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {freshness.map((item) => (
                <tr key={item.assignment_id} className="hover:bg-slate-50/60 transition-colors">
                  <td className="py-2.5 px-4 font-mono text-xs text-slate-900">
                    {item.hostname}
                  </td>
                  <td className="py-2.5 px-4 text-xs text-slate-600">
                    {item.db_type} <span className="text-slate-400">·</span> {item.pool}
                  </td>
                  <td className="py-2.5 px-4 text-xs font-medium text-slate-800">
                    {item.profile_name}
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono text-xs tabular-nums text-slate-600">
                    {item.interval_seconds}s
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono text-xs tabular-nums text-slate-800">
                    {item.staleness_seconds !== null ? `${item.staleness_seconds}s` : 'pending'}{' '}
                    <span className="text-slate-400">/ {item.freshness_slo_seconds}s</span>
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono text-xs tabular-nums text-slate-600">
                    {item.missed_interval_count}
                  </td>
                  <td className="py-2.5 px-4 font-mono text-xs text-slate-500">
                    {formatShortTime(item.last_success_at)}
                  </td>
                  <td className="py-2.5 px-4">
                    <StatusText status={item.slo_compliant ? 'compliant' : 'breach'} />
                  </td>
                </tr>
              ))}
              {freshness.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-xs text-slate-500">
                    No active assignments yet. Run discovery to populate servers and evaluate assignment rules.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Queues & Isolated Worker Pools */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200">
            <h2 className="text-base font-semibold text-slate-900">
              RabbitMQ Queue Topology &amp; Backpressure
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Pause a queue to observe task expiry (expires_at) without late catch-up bursts
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/70 text-xs font-medium text-slate-500">
                  <th className="py-2.5 px-4">Queue</th>
                  <th className="py-2.5 px-4 text-right">Depth</th>
                  <th className="py-2.5 px-4 text-right">Published</th>
                  <th className="py-2.5 px-4 text-right">Acked</th>
                  <th className="py-2.5 px-4 text-right">Expired</th>
                  <th className="py-2.5 px-4 text-right">Control</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {activeQueues.map((q) => (
                  <tr key={q.queue} className="hover:bg-slate-50/60">
                    <td className="py-2.5 px-4 font-mono text-xs text-slate-900">
                      {q.queue}
                      {q.paused && (
                        <span className="ml-2 text-amber-700 font-sans font-medium">
                          (Paused)
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono text-xs tabular-nums">
                      {q.depth}
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono text-xs tabular-nums text-slate-600">
                      {q.published}
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono text-xs tabular-nums text-emerald-700">
                      {q.acked}
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono text-xs tabular-nums text-amber-700">
                      {q.expired}
                    </td>
                    <td className="py-2.5 px-4 text-right">
                      {q.paused ? (
                        <button
                          onClick={() => onResumeQueue(q.queue)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-teal-800 bg-teal-50 hover:bg-teal-100 rounded border border-teal-200 whitespace-nowrap"
                        >
                          <Play className="w-3 h-3" /> Resume
                        </button>
                      ) : (
                        <button
                          onClick={() => onPauseQueue(q.queue)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 rounded border border-slate-200 whitespace-nowrap"
                        >
                          <Pause className="w-3 h-3" /> Pause
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200">
            <h2 className="text-base font-semibold text-slate-900">
              Engine-Isolated Poller Workers &amp; Processors
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              One image per db_type, two pool deployments; HF reuses connections, LF runs isolated
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/70 text-xs font-medium text-slate-500">
                  <th className="py-2.5 px-4">Deployment</th>
                  <th className="py-2.5 px-4 text-right">Processed</th>
                  <th className="py-2.5 px-4 text-right">Conn Hits / Miss</th>
                  <th className="py-2.5 px-4 text-right">Target Cache</th>
                  <th className="py-2.5 px-4 text-right">Secret Cache</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {workers.map((w) => (
                  <tr key={w.worker_id} className="hover:bg-slate-50/60">
                    <td className="py-2.5 px-4">
                      <div className="font-mono text-xs text-slate-900">{w.worker_id}</div>
                      <div className="text-xs text-slate-500">
                        {w.plugin_id} · v{w.plugin_version}
                      </div>
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono text-xs tabular-nums">
                      {w.processed_count}
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono text-xs tabular-nums text-slate-700">
                      {w.connections.cache_hits} / {w.connections.cache_misses}
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono text-xs tabular-nums text-slate-600">
                      {w.target_cache.hits} / {w.target_cache.misses}
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono text-xs tabular-nums text-slate-600">
                      {w.secret_cache.hits} / {w.secret_cache.misses}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="border-t border-slate-200 bg-slate-50/60 px-6 py-3 flex flex-wrap gap-6 text-xs text-slate-600">
            {processors.map((p) => (
              <div key={p.pool} className="font-mono tabular-nums">
                <span className="font-semibold text-slate-800">{p.queue}</span> · ingested{' '}
                {p.processed_count} · rejected {p.rejected_count} · schema_not_ready{' '}
                {p.schema_not_ready_count}
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
