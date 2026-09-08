const STATUS_COLORS: Record<string, string> = {
  active: '#3E8635',
  ready: '#3E8635',
  pass: '#3E8635',
  running: '#3E8635',
  accepted: '#0071C5',
  provisioning: '#0071C5',
  validating: '#0071C5',
  quick_start: '#0071C5',
  submitted: '#6A6E73',
  requested: '#6A6E73',
  reclaimed: '#6A6E73',
  draft: '#6A6E73',
  warn: '#F0AB00',
  expired: '#F0AB00',
  resetting: '#F0AB00',
  paused: '#F0AB00',
  failed: '#C9190B',
  rejected: '#C9190B',
  validation_failed: '#C9190B',
  fail: '#C9190B',
  exited: '#C9190B',
  deprecated: '#C9190B',
  ephemeral: '#6753AC',
  persistent: '#5752D1',
  guided_build: '#6753AC',
  open_sandbox: '#5752D1',
};

export default function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] || '#6A6E73';
  return (
    <span
      className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold text-white"
      style={{ backgroundColor: color }}
    >
      {status.replace(/_/g, ' ')}
    </span>
  );
}
