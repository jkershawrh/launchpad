import type {
  ClusterObservation,
  LlmAttributionObservation,
  LlmModelObservation,
  ProvisioningObservation,
  SeatObservation,
} from './api/types';

export type OperationalTone = 'success' | 'info' | 'warning' | 'danger' | 'muted';

export interface HealthAssessment {
  tone: OperationalTone;
  label: 'healthy' | 'watch' | 'critical' | 'unknown';
  reasons: string[];
}

const ATTENTION_STATUSES = ['failed', 'validation_failed', 'cleanup_failed'];
const INFLIGHT_STATUSES = ['requested', 'pending', 'queued', 'provisioning', 'validating', 'resetting', 'reclaiming'];

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

export function seatHealth(
  seat: SeatObservation,
  traffic: LlmAttributionObservation[],
): HealthAssessment {
  const requests = traffic.reduce((sum, row) => sum + row.requests, 0);
  const errors = traffic.reduce((sum, row) => sum + row.errors, 0);
  const rateLimited = traffic.reduce((sum, row) => sum + row.rate_limited, 0);
  const p95 = Math.max(0, ...traffic.map((row) => row.p95_latency_ms || 0));
  if (ATTENTION_STATUSES.includes(seat.status) || seat.resolution_state === 'attention' || errors > 0) {
    return { tone: 'danger', label: 'critical', reasons: [seat.error || `${errors || 1} failed request${errors === 1 ? '' : 's'}`] };
  }
  const reasons: string[] = [];
  const usage = seat.resource_usage;
  const restarts = usage?.restarts || 0;
  if (usage?.available && (usage.pod_count || 0) > 0 && usage.ready_pods === 0) {
    return { tone: 'danger', label: 'critical', reasons: ['no workload pods ready'] };
  }
  if (INFLIGHT_STATUSES.includes(seat.status)) reasons.push(seat.status.replaceAll('_', ' '));
  if (usage?.available && (usage.ready_pods || 0) < (usage.pod_count || 0)) reasons.push('some workload pods not ready');
  if (restarts > 0) reasons.push(`${restarts} container restarts`);
  if (rateLimited) reasons.push(`${rateLimited} rate limited`);
  if (p95 >= 60_000) reasons.push(`p95 ${Math.round(p95 / 1000)}s`);
  if ((seat.provisioning_seconds || 0) >= 600) reasons.push('slow provisioning');
  if (reasons.length) return { tone: 'warning', label: 'watch', reasons };
  if (['ready', 'active'].includes(seat.status)) {
    return { tone: 'success', label: 'healthy', reasons: [requests ? `${requests} AI requests` : 'ready; no AI traffic yet'] };
  }
  return { tone: 'muted', label: 'unknown', reasons: [seat.status.replaceAll('_', ' ')] };
}

export function modelHealth(
  model: LlmModelObservation,
  traffic: LlmAttributionObservation[],
): HealthAssessment {
  const relevant = traffic.filter((row) => row.model_id === model.model_id);
  const errors = relevant.reduce((sum, row) => sum + row.errors, 0);
  const rateLimited = relevant.reduce((sum, row) => sum + row.rate_limited, 0);
  const p95 = Math.max(0, ...relevant.map((row) => row.p95_latency_ms || 0));
  if (model.ready_replicas === 0 || ['failed', 'unhealthy', 'unreachable'].includes(model.status)) {
    return { tone: 'danger', label: 'critical', reasons: ['no ready serving replicas'] };
  }
  const reasons: string[] = [];
  if (model.ready_replicas < model.desired_replicas) reasons.push('replicas below desired');
  if (errors) reasons.push(`${errors} errors`);
  if (rateLimited) reasons.push(`${rateLimited} rate limited`);
  if (p95 >= 60_000) reasons.push(`p95 ${Math.round(p95 / 1000)}s`);
  if (reasons.length) return { tone: 'warning', label: 'watch', reasons };
  return { tone: 'success', label: 'healthy', reasons: ['replicas ready'] };
}

export function clusterHealth(cluster: ClusterObservation): HealthAssessment {
  if (!cluster.healthy) {
    return { tone: 'danger', label: 'critical', reasons: [cluster.reason || 'cluster unreachable'] };
  }
  const reasons: string[] = [];
  if (!cluster.eligible) reasons.push(cluster.reason || 'placement disabled');
  if (cluster.available_cpu_millicores < 20_000) reasons.push('CPU headroom below 20 cores');
  if (cluster.available_memory_mib < 32_768) reasons.push('memory headroom below 32 GiB');
  if (cluster.available_pods < 50) reasons.push('fewer than 50 pod slots');
  if (reasons.length) return { tone: 'warning', label: 'watch', reasons };
  return { tone: 'success', label: 'healthy', reasons: ['placement headroom available'] };
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
