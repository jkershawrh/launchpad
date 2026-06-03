export interface InferenceRequest {
  id: string;
  task: string;
  model: string;
  model_size_b: number;
  backend: string;
  accelerator: string;
  status: 'success' | 'error';
  latency_ms: number;
  cost_estimate: number;
  reason: string;
  error_detail: string | null;
  created_at: string;
}

export interface GovernanceDecision {
  id: string;
  request_id: string | null;
  source: string;
  intent: string;
  risk_score: number;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  decision: string;
  reason: string;
  evidence: Record<string, unknown>;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
}

export interface BackendInfo {
  name: string;
  url: string;
  accelerator: string;
  capabilities: string[];
  cost_per_1k_tokens: number;
  healthy: boolean;
}

export interface RoutingRule {
  id: string;
  task: string;
  backend_id: string;
  condition_type: 'static' | 'size_based';
  condition_json: Record<string, unknown> | null;
  reason: string;
  active: boolean;
  priority: number;
  created_at: string;
}

export interface RoutingMetadata {
  selected_backend: string;
  accelerator: string;
  reason: string;
  latency_ms: number;
  cost_estimate_per_1k_tokens: number;
  task: string;
}

export interface RouteResponse {
  result: unknown;
  routing: RoutingMetadata;
  error: string | null;
}

export interface HealthStatus {
  status: string;
  backends: number;
  routes: number;
  version: string;
}

export interface CostSummaryItem {
  backend: string;
  task: string;
  request_count: number;
  total_cost: number;
  avg_latency_ms: number;
  avg_cost_per_request?: number;
}

export interface LatencyPercentiles {
  backend: string;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  sample_count: number;
}

export interface RoutingDistribution {
  backend: string;
  count: number;
  pct: number;
}

export interface GovernanceSummaryItem {
  decision: string;
  count: number;
  pct: number;
}

export interface PaginatedResponse<T> {
  data: T[];
  page: number;
  per_page: number;
}

export interface AnalyticsResponse<T> {
  data: T[];
  period_days: number;
}

export interface Route {
  task: string;
  backend?: string;
  default_backend?: string;
  conditions?: Record<string, unknown>;
  reason: string;
}

export type Accelerator = 'xeon6' | 'gaudi' | 'local';
export type TaskType = 'embeddings' | 'classification' | 'reranking' | 'completion' | 'batch_generation';

// Intelligence layer types
export interface ClusterCapacity {
  cluster_name: string;
  score: number;
  cpu_utilization?: number;
  gpu_available?: boolean;
  health_status: string;
  last_updated: string;
}

export interface DeepFieldSignal {
  cluster_name: string;
  metric_type: string;
  value: number;
  threshold: number;
  status: 'normal' | 'warning' | 'critical';
  timestamp: string;
}

export interface HealthAlert {
  alert_id: string;
  cluster_name: string;
  alert_type: string;
  severity: 'info' | 'warning' | 'critical';
  recommended_action: string;
  signals: DeepFieldSignal[];
  created_at: string;
}

export interface FleetHealthResponse {
  clusters: ClusterCapacity[];
  alerts: HealthAlert[];
}

export interface FeedbackSummary {
  catalog_item_id: string;
  cluster_name: string;
  hardware_profile: string;
  total_attempts: number;
  success_count: number;
  success_rate: number;
  avg_latency_ms: number;
  last_failure_reason?: string;
  confidence: number;
  recommendation: 'preferred' | 'acceptable' | 'avoid';
}
