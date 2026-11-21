import { useEffect, useState } from 'react';
import { api } from '../api';
import { StatusText, formatShortTime } from './StatusText';

const ENGINE_TABLES: Record<string, string[]> = {
  postgresql: ['instance_health', 'connections', 'replication_lag', 'table_statistics', 'database_capacity'],
  oracle: ['instance_health', 'active_sessions', 'wait_events', 'tablespace_usage'],
  mssql: ['instance_health', 'user_connections', 'buffer_pool', 'database_file_sizes'],
};

export function MetricsReportingView() {
  const [reportingRows, setReportingRows] = useState<Array<{
    db_type: string;
    server_id: string;
    hostname: string;
    environment: string;
    polling_run_id: string;
    collected_at: string;
    is_available: number;
    response_time_ms: number | null;
  }>>([]);
  const [selectedEngine, setSelectedEngine] = useState('postgresql');
  const [selectedTable, setSelectedTable] = useState('connections');
  const [metricData, setMetricData] = useState<{
    table: string;
    rows: Array<Record<string, unknown>>;
    partitions: Array<Record<string, unknown>>;
  } | null>(null);
  const [maintStatus, setMaintStatus] = useState<string | null>(null);

  // Appendix B Sizing Calculator
  const [serversCount, setServersCount] = useState(1000);
  const [hfInterval, setHfInterval] = useState(60);
  const [hfRowsPerPoll, setHfRowsPerPoll] = useState(20);
  const [lfInterval, setLfInterval] = useState(900);
  const [lfRowsPerPoll, setLfRowsPerPoll] = useState(200);
  const [hfRetentionDays, setHfRetentionDays] = useState(14);

  const loadData = async (eng: string, tbl: string) => {
    const [rep, met] = await Promise.all([
      api.getReportingHealth(),
      api.getMetricTable(eng, tbl),
    ]);
    setReportingRows(rep.rows);
    setMetricData(met);
  };

  useEffect(() => {
    loadData(selectedEngine, selectedTable).catch(() => {});
  }, [selectedEngine, selectedTable]);

  const handleEngineChange = (eng: string) => {
    setSelectedEngine(eng);
    setSelectedTable(ENGINE_TABLES[eng][0]);
  };

  const handleRunMaintenance = async () => {
    const res = await api.runMaintenance();
    setMaintStatus(
      `Maintenance cycle complete: ${res.created_partitions} partition windows ensured, ${res.pruned_outbox} outbox rows pruned.`
    );
    await loadData(selectedEngine, selectedTable);
  };

  const hfPollsPerSec = serversCount / Math.max(1, hfInterval);
  const hfPollsPerDay = hfPollsPerSec * 86400;
  const hfRowsPerDay = hfPollsPerDay * hfRowsPerPoll;
  const lfPollsPerSec = serversCount / Math.max(1, lfInterval);
  const lfPollsPerDay = lfPollsPerSec * 86400;
  const lfRowsPerDay = lfPollsPerDay * lfRowsPerPoll;
  const hfRetainedRows = hfRowsPerDay * hfRetentionDays;

  return (
    <div className="space-y-8">
      {/* Cross-Engine Reporting View */}
      <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-900">
              Cross-Engine View: reporting.instance_health
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              SQL UNION ALL across metrics_postgresql, metrics_oracle, and metrics_mssql
            </p>
          </div>
          <div className="text-xs font-mono text-slate-500 tabular-nums">
            {reportingRows.length} recent samples
          </div>
        </div>
        <div className="overflow-x-auto max-h-72 overflow-y-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead className="sticky top-0 bg-slate-50 border-b border-slate-200 text-xs font-medium text-slate-500">
              <tr>
                <th className="py-2.5 px-4">Server</th>
                <th className="py-2.5 px-4">Engine · Env</th>
                <th className="py-2.5 px-4">Availability</th>
                <th className="py-2.5 px-4 text-right">Response Time</th>
                <th className="py-2.5 px-4">Run ID</th>
                <th className="py-2.5 px-4">Collected At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {reportingRows.map((r, idx) => (
                <tr key={`${r.polling_run_id}-${idx}`} className="hover:bg-slate-50/60">
                  <td className="py-2 px-4 font-mono text-xs text-slate-900">{r.hostname}</td>
                  <td className="py-2 px-4 text-xs text-slate-600">
                    {r.db_type} · {r.environment}
                  </td>
                  <td className="py-2 px-4">
                    <StatusText status={r.is_available ? 'succeeded' : 'failed'} />
                  </td>
                  <td className="py-2 px-4 text-right font-mono text-xs tabular-nums">
                    {r.response_time_ms ?? '—'} ms
                  </td>
                  <td className="py-2 px-4 font-mono text-xs text-slate-500">
                    {r.polling_run_id.slice(0, 8)}
                  </td>
                  <td className="py-2 px-4 font-mono text-xs text-slate-500">
                    {formatShortTime(r.collected_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Plugin-Owned Metric Table Explorer + Partition Catalog */}
      <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900">
              Plugin-Owned Metric Schemas &amp; Partition Retention
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Declaratively ingested with ON CONFLICT DO NOTHING and zero cross-schema foreign keys
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={selectedEngine}
              onChange={(e) => handleEngineChange(e.target.value)}
              className="text-xs border border-slate-200 rounded px-3 py-1.5 bg-white font-mono"
            >
              {Object.keys(ENGINE_TABLES).map((eng) => (
                <option key={eng} value={eng}>
                  metrics_{eng}
                </option>
              ))}
            </select>
            <select
              value={selectedTable}
              onChange={(e) => setSelectedTable(e.target.value)}
              className="text-xs border border-slate-200 rounded px-3 py-1.5 bg-white font-mono"
            >
              {ENGINE_TABLES[selectedEngine].map((tbl) => (
                <option key={tbl} value={tbl}>
                  {tbl}
                </option>
              ))}
            </select>
            <button
              onClick={handleRunMaintenance}
              className="px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 rounded"
            >
              Run Maintenance
            </button>
          </div>
        </div>

        {maintStatus && (
          <div className="px-6 py-2.5 bg-teal-50 border-b border-teal-200 text-xs text-teal-900">
            {maintStatus}
          </div>
        )}

        <div className="p-6 space-y-4">
          {metricData && (
            <>
              <div className="text-xs text-slate-600 font-mono">
                Active Partitions ({metricData.partitions.length}):{' '}
                {metricData.partitions
                  .slice(0, 4)
                  .map((p) => `${String(p.partition_name)} (${String(p.retention_days)}d)`)
                  .join(' · ')}
              </div>
              <div className="overflow-x-auto border border-slate-200 rounded">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-slate-500">
                      <th className="py-2 px-3">Server</th>
                      <th className="py-2 px-3">Collected At</th>
                      <th className="py-2 px-3">Engine Columns</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {metricData.rows.slice(0, 15).map((row, i) => {
                      const { hostname, server_id, polling_run_id, collected_at, ...metrics } = row;
                      return (
                        <tr key={i}>
                          <td className="py-2 px-3 font-mono text-slate-900">
                            {String(hostname || server_id)}
                          </td>
                          <td className="py-2 px-3 font-mono text-slate-500">
                            {formatShortTime(String(collected_at))}
                          </td>
                          <td className="py-2 px-3 font-mono text-slate-700">
                            {JSON.stringify(metrics)}
                          </td>
                        </tr>
                      );
                    })}
                    {metricData.rows.length === 0 && (
                      <tr>
                        <td colSpan={3} className="py-6 text-center text-slate-500">
                          No rows ingested for {metricData.table} yet. Trigger a manual poll to populate immediately.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </section>

      {/* Appendix B Sizing Calculator */}
      <section className="bg-white border border-slate-200 rounded-lg p-6 space-y-5">
        <div>
          <h2 className="text-base font-semibold text-slate-900">
            Appendix B — Capacity &amp; Partition Sizing Calculator
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Model sustained RabbitMQ message rates and PostgreSQL partition volume across server scale
          </p>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Servers</label>
            <input
              type="number"
              min={1}
              value={serversCount}
              onChange={(e) => setServersCount(Number(e.target.value))}
              className="w-full text-xs border border-slate-200 rounded px-2.5 py-1.5 font-mono tabular-nums"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">HF Interval (s)</label>
            <input
              type="number"
              min={30}
              value={hfInterval}
              onChange={(e) => setHfInterval(Number(e.target.value))}
              className="w-full text-xs border border-slate-200 rounded px-2.5 py-1.5 font-mono tabular-nums"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">HF Rows/Poll</label>
            <input
              type="number"
              min={1}
              value={hfRowsPerPoll}
              onChange={(e) => setHfRowsPerPoll(Number(e.target.value))}
              className="w-full text-xs border border-slate-200 rounded px-2.5 py-1.5 font-mono tabular-nums"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">LF Interval (s)</label>
            <input
              type="number"
              min={60}
              value={lfInterval}
              onChange={(e) => setLfInterval(Number(e.target.value))}
              className="w-full text-xs border border-slate-200 rounded px-2.5 py-1.5 font-mono tabular-nums"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">LF Rows/Poll</label>
            <input
              type="number"
              min={1}
              value={lfRowsPerPoll}
              onChange={(e) => setLfRowsPerPoll(Number(e.target.value))}
              className="w-full text-xs border border-slate-200 rounded px-2.5 py-1.5 font-mono tabular-nums"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">HF Retention (d)</label>
            <input
              type="number"
              min={1}
              value={hfRetentionDays}
              onChange={(e) => setHfRetentionDays(Number(e.target.value))}
              className="w-full text-xs border border-slate-200 rounded px-2.5 py-1.5 font-mono tabular-nums"
            />
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 border-t border-slate-200 pt-4 text-xs">
          <div>
            <div className="text-slate-500">High-Frequency Load</div>
            <div className="font-mono font-semibold text-slate-900 mt-1 tabular-nums">
              {hfPollsPerSec.toFixed(1)} polls/s · {(hfPollsPerDay / 1e6).toFixed(2)}M polls/day ·{' '}
              {(hfRowsPerDay / 1e6).toFixed(1)}M rows/day
            </div>
          </div>
          <div>
            <div className="text-slate-500">Low-Frequency Load</div>
            <div className="font-mono font-semibold text-slate-900 mt-1 tabular-nums">
              {lfPollsPerSec.toFixed(1)} polls/s · {(lfPollsPerDay / 1e3).toFixed(0)}K polls/day ·{' '}
              {(lfRowsPerDay / 1e6).toFixed(1)}M rows/day
            </div>
          </div>
          <div>
            <div className="text-slate-500">{hfRetentionDays}-Day HF Partition Footprint</div>
            <div className="font-mono font-semibold text-teal-800 mt-1 tabular-nums">
              {(hfRetainedRows / 1e6).toFixed(0)}M retained rows (partition drop required)
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
