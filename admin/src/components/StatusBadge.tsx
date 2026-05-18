const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-100 text-green-800',
  ready: 'bg-green-100 text-green-800',
  pass: 'bg-green-100 text-green-800',
  accepted: 'bg-blue-100 text-blue-800',
  provisioning: 'bg-blue-100 text-blue-800',
  validating: 'bg-yellow-100 text-yellow-800',
  submitted: 'bg-gray-100 text-gray-800',
  requested: 'bg-gray-100 text-gray-800',
  ephemeral: 'bg-purple-100 text-purple-800',
  persistent: 'bg-indigo-100 text-indigo-800',
  expired: 'bg-orange-100 text-orange-800',
  resetting: 'bg-orange-100 text-orange-800',
  reclaimed: 'bg-gray-100 text-gray-600',
  failed: 'bg-red-100 text-red-800',
  rejected: 'bg-red-100 text-red-800',
  validation_failed: 'bg-red-100 text-red-800',
  warn: 'bg-yellow-100 text-yellow-800',
  fail: 'bg-red-100 text-red-800',
  running: 'bg-green-100 text-green-800',
  exited: 'bg-red-100 text-red-800',
  paused: 'bg-yellow-100 text-yellow-800',
  draft: 'bg-gray-100 text-gray-800',
  deprecated: 'bg-orange-100 text-orange-800',
  quick_start: 'bg-blue-100 text-blue-800',
  guided_build: 'bg-purple-100 text-purple-800',
  open_sandbox: 'bg-indigo-100 text-indigo-800',
};

export default function StatusBadge({ status }: { status: string }) {
  const colors = STATUS_COLORS[status] || 'bg-gray-100 text-gray-800';
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colors}`}>
      {status.replace(/_/g, ' ')}
    </span>
  );
}
