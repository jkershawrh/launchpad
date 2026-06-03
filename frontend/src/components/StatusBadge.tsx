const STATUS_COLORS: Record<string, string> = {
  ready: '#3E8635',
  active: '#3E8635',
  pass: '#3E8635',
  healthy: '#3E8635',
  preferred: '#3E8635',
  accepted: '#0071C5',
  provisioning: '#0071C5',
  validating: '#0071C5',
  info: '#0071C5',
  submitted: '#6A6E73',
  requested: '#6A6E73',
  reclaimed: '#6A6E73',
  skipped: '#6A6E73',
  warn: '#F0AB00',
  warning: '#F0AB00',
  acceptable: '#F0AB00',
  expired: '#F0AB00',
  resetting: '#F0AB00',
  failed: '#C9190B',
  fail: '#C9190B',
  rejected: '#C9190B',
  validation_failed: '#C9190B',
  cleanup_failed: '#C9190B',
  critical: '#C9190B',
  avoid: '#C9190B',
};

export default function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] || '#6A6E73';
  return (
    <span
      className="px-2 py-0.5 rounded text-xs font-semibold text-white"
      style={{ backgroundColor: color }}
    >
      {status.replace(/_/g, ' ')}
    </span>
  );
}
