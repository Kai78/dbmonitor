import { useState } from 'react';
import type { CIReport, PluginRegistryItem, PluginSchemaVersion } from '../types';

interface PluginsBundlesViewProps {
  plugins: PluginRegistryItem[];
  schemaVersions: PluginSchemaVersion[];
  bundles: Record<
    string,
    {
      files: string[];
      schema_manifest?: Record<string, unknown>;
      migrations?: Record<string, string>;
    }
  >;
  onTogglePlugin: (pluginId: string, enabled: boolean, pools: string[]) => Promise<void>;
  onRunCiVerify: () => Promise<CIReport>;
}

export function PluginsBundlesView({
  plugins,
  schemaVersions,
  bundles,
  onTogglePlugin,
  onRunCiVerify,
}: PluginsBundlesViewProps) {
  const [selectedPluginId, setSelectedPluginId] = useState<string>('dbmonitor-poller-postgresql');
  const [ciReport, setCiReport] = useState<CIReport | null>(null);
  const [runningCi, setRunningCi] = useState(false);

  const selectedBundle = bundles[selectedPluginId];

  const handleRunCi = async () => {
    setRunningCi(true);
    try {
      const rep = await onRunCiVerify();
      setCiReport(rep);
    } finally {
      setRunningCi(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* CI Gate Runner */}
      <section className="bg-white border border-slate-200 rounded-lg p-6 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900">
              Architecture &amp; SDK Contract CI Gates
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Runs AST import boundary verification (check_import_boundaries.py) and SDK provider/poller/profile/schema contract suites
            </p>
          </div>
          <button
            onClick={handleRunCi}
            disabled={runningCi}
            className="px-4 py-2 text-xs font-medium text-white bg-teal-700 hover:bg-teal-800 disabled:opacity-50 rounded-md whitespace-nowrap"
          >
            {runningCi ? 'Running Gates...' : 'Run Boundary & Contract Gates'}
          </button>
        </div>

        {ciReport && (
          <div className="border-t border-slate-200 pt-4 space-y-3 text-xs">
            <div className="flex items-center justify-between">
              <div className="font-semibold text-slate-900">
                AST Import Boundaries:{' '}
                <span className={ciReport.import_boundaries.passed ? 'text-emerald-700' : 'text-rose-700'}>
                  {ciReport.import_boundaries.passed ? 'PASSED' : 'FAILED'}
                </span>
              </div>
              <div className="font-mono text-slate-500 tabular-nums">
                {ciReport.import_boundaries.checked_files} Python files inspected ·{' '}
                {ciReport.import_boundaries.violations.length} violations
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {ciReport.contract_tests.map((ct) => (
                <div key={ct.plugin_id} className="border border-slate-200 rounded p-3 bg-slate-50/50">
                  <div className="font-mono font-semibold text-slate-900">{ct.plugin_id}</div>
                  <div className="text-emerald-700 font-medium mt-0.5">
                    {ct.passed ? 'Contracts Passed' : 'Failed'}
                  </div>
                  <ul className="mt-2 space-y-1 text-slate-600">
                    {ct.checks.map((chk, idx) => (
                      <li key={idx}>· {chk}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Plugin Registry */}
      <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200">
          <h2 className="text-base font-semibold text-slate-900">
            Plugin Registry &amp; Pool Enablement
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Loaded from data-only plugin bundles. Disabling a pool causes scheduler runs for that combination to be explicitly rejected.
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/70 text-xs font-medium text-slate-500">
                <th className="py-2.5 px-4">Plugin ID</th>
                <th className="py-2.5 px-4">Kind · Target</th>
                <th className="py-2.5 px-4">Version · Schema</th>
                <th className="py-2.5 px-4">Enabled Pools</th>
                <th className="py-2.5 px-4 text-right">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {plugins.map((p) => {
                const pools: string[] = JSON.parse(p.enabled_pools_json || '[]');
                return (
                  <tr
                    key={p.plugin_id}
                    onClick={() => setSelectedPluginId(p.plugin_id)}
                    className={`hover:bg-slate-50/60 cursor-pointer ${
                      selectedPluginId === p.plugin_id ? 'bg-slate-50' : ''
                    }`}
                  >
                    <td className="py-2.5 px-4 font-mono text-xs font-semibold text-slate-900">
                      {p.plugin_id}
                    </td>
                    <td className="py-2.5 px-4 text-xs text-slate-600">
                      {p.kind} · {p.db_type || p.provider_name}
                    </td>
                    <td className="py-2.5 px-4 font-mono text-xs text-slate-600">
                      v{p.version} {p.schema_version ? `· schema ${p.schema_version}` : ''}
                    </td>
                    <td className="py-2.5 px-4 space-x-2" onClick={(e) => e.stopPropagation()}>
                      {p.kind === 'poller' ? (
                        ['high_frequency', 'low_frequency'].map((poolName) => {
                          const active = pools.includes(poolName);
                          const next = active
                            ? pools.filter((x) => x !== poolName)
                            : [...pools, poolName];
                          return (
                            <button
                              key={poolName}
                              onClick={() => onTogglePlugin(p.plugin_id, Boolean(p.enabled), next)}
                              className={`px-2 py-1 text-xs font-mono rounded border ${
                                active
                                  ? 'bg-teal-50 border-teal-200 text-teal-900'
                                  : 'bg-white border-slate-200 text-slate-400'
                              }`}
                            >
                              {poolName}
                            </button>
                          );
                        })
                      ) : (
                        <span className="text-xs text-slate-400">discovery</span>
                      )}
                    </td>
                    <td className="py-2.5 px-4 text-right" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => onTogglePlugin(p.plugin_id, !p.enabled, pools)}
                        className={`px-2.5 py-1 text-xs font-medium rounded border ${
                          p.enabled
                            ? 'text-emerald-800 bg-emerald-50 border-emerald-200'
                            : 'text-rose-800 bg-rose-50 border-rose-200'
                        }`}
                      >
                        {p.enabled ? 'Enabled' : 'Disabled'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Data-Only Bundle & Migration Inspector */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <section className="bg-white border border-slate-200 rounded-lg p-6 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-slate-900">
              Data-Only Bundle: <span className="font-mono">{selectedPluginId}</span>
            </h2>
            <span className="text-xs text-slate-500">Zero plugin Python code</span>
          </div>
          {selectedBundle ? (
            <>
              <div className="text-xs font-mono text-slate-600">
                Artifacts: {selectedBundle.files.join(' · ')}
              </div>
              {selectedBundle.schema_manifest && (
                <pre className="p-3 bg-slate-50 border border-slate-200 rounded text-[11px] overflow-x-auto max-h-72">
                  {JSON.stringify(selectedBundle.schema_manifest, null, 2)}
                </pre>
              )}
            </>
          ) : (
            <div className="text-xs text-slate-500">Select a plugin above to inspect its bundle.</div>
          )}
        </section>

        <section className="bg-white border border-slate-200 rounded-lg p-6 space-y-3">
          <h2 className="text-base font-semibold text-slate-900">
            Applied Schema Versions &amp; DDL Migrations
          </h2>
          <div className="divide-y divide-slate-100 border border-slate-200 rounded">
            {schemaVersions.map((sv) => (
              <div key={sv.namespace} className="px-4 py-2.5 text-xs flex items-center justify-between">
                <div className="font-mono text-slate-900">{sv.namespace}</div>
                <div className="font-mono text-slate-600">
                  v{sv.schema_version} · {sv.plugin_id}
                </div>
              </div>
            ))}
          </div>
          {selectedBundle?.migrations &&
            Object.entries(selectedBundle.migrations).map(([fname, sql]) => (
              <div key={fname} className="space-y-1">
                <div className="text-xs font-mono font-semibold text-slate-700">{fname}</div>
                <pre className="p-3 bg-slate-50 border border-slate-200 rounded text-[11px] overflow-x-auto max-h-56">
                  {sql}
                </pre>
              </div>
            ))}
        </section>
      </div>
    </div>
  );
}
