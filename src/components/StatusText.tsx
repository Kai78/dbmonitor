interface StatusTextProps {
  status: string;
}

const STATUS_STYLES: Record<string, { color: string; label: string }> = {
  succeeded: { color: 'text-emerald-700', label: 'Succeeded' },
  active: { color: 'text-emerald-700', label: 'Active' },
  compliant: { color: 'text-emerald-700', label: 'Within SLO' },
  partially_succeeded: { color: 'text-amber-700', label: 'Partial' },
  queued: { color: 'text-sky-700', label: 'Queued' },
  running: { color: 'text-sky-700', label: 'Running' },
  requested: { color: 'text-slate-600', label: 'Requested' },
  dispatched: { color: 'text-slate-700', label: 'Dispatched' },
  expired: { color: 'text-amber-700', label: 'Expired' },
  lost: { color: 'text-rose-700', label: 'Lost' },
  failed: { color: 'text-rose-700', label: 'Failed' },
  rejected: { color: 'text-rose-700', label: 'Rejected' },
  cancelled: { color: 'text-slate-500', label: 'Cancelled' },
  retired: { color: 'text-slate-500', label: 'Retired' },
  breach: { color: 'text-rose-700', label: 'SLO Breach' },
};

export function StatusText({ status }: StatusTextProps) {
  const key = status.toLowerCase();
  const cfg = STATUS_STYLES[key] ?? { color: 'text-slate-700', label: status };
  return (
    <span className={`font-medium text-xs whitespace-nowrap ${cfg.color}`}>
      {cfg.label}
    </span>
  );
}

export function formatShortTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toISOString().slice(11, 19) + 'Z';
  } catch {
    return iso;
  }
}
