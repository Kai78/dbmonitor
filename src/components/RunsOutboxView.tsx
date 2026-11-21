import { useState } from 'react';
import type { DiscoveryRun, ManualRunRequest, OutboxRow, PollingRun } from '../types';
import { StatusText, formatShortTime } from './StatusText';

interface RunsOutboxViewProps {
  pollingRuns: PollingRun[];
  discoveryRuns: DiscoveryRun[];
  manualRequests: ManualRunRequest[];
  outbox: OutboxRow[];
  dlqMessages: Array<Record<string, unknown>>;
  statusFilter: string;
  onStatusFilterChange: (s: string) => void;
  onCancelRun: (runId: string) => Promise<void>;
  onRetryRun: (runId: string) => Promise<void>;
  onDrainDlq: (queue: string) => Promise<void>;
}

const RUN_FILTERS = [
  { id: '', label: 'All' },
  { id: 'succeeded', label: 'Succeeded' },
  { id: 'partially_succeeded', label: 'Partial' },
  { id: 'failed', label: 'Failed' },
  { id: 'queued', label: 'Queued' },
  { id: 'expired', label: 'Expired' },
  { id: 'lost', label: 'Lost' },
  { id: 'rejected', label: 'Rejected' },
];

export function RunsOutboxView({
  pollingRuns,
  discoveryRuns,
  manualRequests,
  outbox,
  dlqMessages,
  statusFilter,
  onStatusFilterChange,
  onCancelRun,
  onRetryRun,
  onDrainDlq,
}: RunsOutboxViewProps) {
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);

  return (
    <div className="space-y-8">
      {/* Polling Runs */}
      <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Polling Runs</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Scheduled and manual runs share the same outbox, queue, and worker execution path
            </p>
          </div>
          <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg overflow-x-auto">
            {RUN_FILTERS.map((f) => (
              <button
                key={f.id || 'all'}
                onClick={() => onStatusFilterChange(f.id)}
                className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${
                  statusFilter === f.id
                    ? 'bg-white text-slate-900 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/70 text-xs font-medium text-slate-500">
                <th className="py-2.5 px-4">Run ID</th>
                <th className="py-2.5 px-4">Server</th>
                <th className="py-2.5 px-4">Engine · Pool</th>
                <th className="py-2.5 px-4">Trigger</th>
                <th className="py-2.5 px-4 text-right">Att</th>
                <th className="py-2.5 px-4">Status</th>
                <th className="py-2.5 px-4">Finished</th>
                <th className="py-2.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {pollingRuns.map((r) => {
                const isExpanded = expandedRunId === r.polling_run_id;
                return (
                  <>
                    <tr
                      key={r.polling_run_id}
                      onClick={() =>
                        setExpandedRunId(isExpanded ? null : r.polling_run_id)
                      }
                      className="hover:bg-slate-50/60 cursor-pointer"
                    >
                      <td className="py-2.5 px-4 font-mono text-xs text-slate-700">
                        {r.polling_run_id.slice(0, 8)}
                      </td>
                      <td className="py-2.5 px-4 font-mono text-xs text-slate-900">
                        {r.hostname || r.server_id.slice(0, 8)}
                      </td>
                      <td className="py-2.5 px-4 text-xs text-slate-600">
                        {r.db_type} <span className="text-slate-400">·</span> {r.pool}
                      </td>
                      <td className="py-2.5 px-4 text-xs text-slate-600">
                        {r.trigger}
                        {r.requested_by ? ` (${r.requested_by})` : ''}
                      </td>
                      <td className="py-2.5 px-4 text-right font-mono text-xs tabular-nums">
                        {r.attempt_count}
                      </td>
                      <td className="py-2.5 px-4">
                        <StatusText status={r.status} />
                        {r.error_category && (
                          <span className="ml-2 font-mono text-xs text-rose-700">
                            {r.error_category}
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 px-4 font-mono text-xs text-slate-500">
                        {formatShortTime(r.finished_at || r.created_at)}
                      </td>
                      <td
                        className="py-2.5 px-4 text-right space-x-2"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {r.status === 'queued' && (
                          <button
                            onClick={() => onCancelRun(r.polling_run_id)}
                            className="px-2.5 py-1 text-xs font-medium text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 rounded"
                          >
                            Cancel
                          </button>
                        )}
                        <button
                          onClick={() => onRetryRun(r.polling_run_id)}
                          className="px-2.5 py-1 text-xs font-medium text-teal-800 bg-teal-50 border border-teal-200 hover:bg-teal-100 rounded"
                        >
                          Retry
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr key={`${r.polling_run_id}-detail`} className="bg-slate-50/70">
                        <td colSpan={8} className="px-6 py-4 text-xs">
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                              <div className="font-semibold text-slate-700 mb-1">
                                Run Metadata
                              </div>
                              <div className="font-mono text-slate-600 space-y-1">
                                <div>polling_run_id: {r.polling_run_id}</div>
                                <div>groups: {r.collector_groups_json}</div>
                                <div>expires_at: {r.expires_at || '—'}</div>
                                {r.error_message && (
                                  <div className="text-rose-700">error: {r.error_message}</div>
                                )}
                              </div>
                            </div>
                            <div>
                              <div className="font-semibold text-slate-700 mb-1">
                                Collectors Output
                              </div>
                              <pre className="p-2.5 bg-white border border-slate-200 rounded text-[11px] overflow-x-auto max-h-40">
                                {r.collectors_json
                                  ? JSON.stringify(JSON.parse(r.collectors_json), null, 2)
                                  : 'Awaiting result...'}
                              </pre>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Manual Run Requests & Transactional Outbox */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200">
            <h2 className="text-base font-semibold text-slate-900">
              Manual Run Requests &amp; Discovery History
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              API persists manual_run_requests (202 Accepted) and lets scheduler claim them
            </p>
          </div>
          <div className="divide-y divide-slate-100 max-h-72 overflow-y-auto">
            {manualRequests.map((m) => (
              <div key={m.request_id} className="px-5 py-3 text-xs flex items-center justify-between gap-4">
                <div>
                  <div className="font-mono text-slate-900">
                    {m.kind} · {m.request_id.slice(0, 8)} · by {m.requested_by}
                  </div>
                  <div className="font-mono text-slate-500 mt-0.5">
                    scope={m.scope_json}
                  </div>
                </div>
                <StatusText status={m.status} />
              </div>
            ))}
            {discoveryRuns.slice(0, 6).map((d) => (
              <div key={d.discovery_run_id} className="px-5 py-3 text-xs flex items-center justify-between gap-4 bg-slate-50/40">
                <div>
                  <div className="font-mono text-slate-900">
                    discovery · {d.provider_name} · {d.trigger}
                    {d.dry_run ? ' (dry-run)' : ''}
                  </div>
                  <div className="text-slate-500 mt-0.5">
                    discovered {d.discovered_count} · created {d.created_count} · updated {d.updated_count}
                  </div>
                </div>
                <StatusText status={d.status} />
              </div>
            ))}
          </div>
        </section>

        <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-slate-900">
                Transactional Outbox &amp; Dead-Letter Queues
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Atomic run + outbox commit; rejected or schema-not-ready messages route to dlq.*
              </p>
            </div>
            {dlqMessages.length > 0 && (
              <button
                onClick={() => onDrainDlq(String(dlqMessages[0].queue))}
                className="px-3 py-1 text-xs font-medium text-rose-800 bg-rose-50 border border-rose-200 hover:bg-rose-100 rounded"
              >
                Drain DLQ ({dlqMessages.length})
              </button>
            )}
          </div>
          <div className="divide-y divide-slate-100 max-h-72 overflow-y-auto">
            {dlqMessages.map((msg, idx) => (
              <div key={idx} className="px-5 py-3 text-xs bg-rose-50/40">
                <div className="font-mono font-semibold text-rose-800">
                  {String(msg.queue)} · reason: {String(msg.reason)}
                </div>
                <pre className="mt-1 font-mono text-[11px] text-slate-600 overflow-x-auto">
                  {JSON.stringify(msg.payload).slice(0, 180)}
                </pre>
              </div>
            ))}
            {outbox.slice(0, 12).map((o) => (
              <div key={o.outbox_id} className="px-5 py-2.5 text-xs flex items-center justify-between">
                <div className="font-mono text-slate-800">
                  {o.queue_name} · {o.outbox_id.slice(0, 8)}
                </div>
                <div className="font-mono text-slate-500">
                  {o.published_at ? `relayed ${formatShortTime(o.published_at)}` : 'pending relay'}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
