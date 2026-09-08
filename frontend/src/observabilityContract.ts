import type { ProvisioningObservation } from './api/types';

export type OperationalTone = 'success' | 'info' | 'warning' | 'danger' | 'muted';

export function filterProvisioning(
  labs: ProvisioningObservation[],
  query: string,
): ProvisioningObservation[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return labs;
  return labs.filter((lab) => [
    lab.name,
    lab.catalog_item_id,
    lab.cluster_ref || '',
    lab.order_id,
  ].some((value) => value.toLowerCase().includes(normalized)));
}

export function formatOperationalDuration(seconds?: number | null): string {
  if (seconds == null) return '—';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

export function statusTone(status: string): OperationalTone {
  if (['ready', 'active', 'healthy', 'eligible', 'resolved'].includes(status)) return 'success';
  if (['requested', 'pending', 'queued', 'provisioning', 'validating'].includes(status)) return 'info';
  if (['resetting', 'reclaiming', 'degraded', 'warning'].includes(status)) return 'warning';
  if (['failed', 'validation_failed', 'cleanup_failed', 'unreachable', 'attention'].includes(status)) return 'danger';
  return 'muted';
}

export function grafanaDrilldownUrl(
  baseUrl: string | null | undefined,
  lab: ProvisioningObservation,
): string | null {
  if (!baseUrl) return null;
  let url: URL;
  try {
    url = new URL(baseUrl);
  } catch {
    return null;
  }
  if (lab.cluster_ref) url.searchParams.set('var-cluster', lab.cluster_ref);
  url.searchParams.set('var-catalog', lab.catalog_item_id);
  return url.toString();
}
