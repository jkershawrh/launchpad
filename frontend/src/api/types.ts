export interface Tenant {
  tenant_id: string;
  display_name: string;
  tenant_type: string;
  status: string;
  branding_profile_id?: string;
  default_quota_profile?: string;
  default_ttl?: string;
  cost_center?: string;
}

export interface CatalogItem {
  catalog_item_id: string;
  display_name: string;
  description: string;
  category: 'quick_start' | 'guided_build' | 'open_sandbox';
  version: string;
  status: string;
  required_capabilities: string[];
  optional_capabilities: string[];
  default_hardware_profile?: string;
  default_quota_profile?: string;
  default_ttl?: string;
  metadata?: Record<string, unknown>;
}

export interface LabRequest {
  request_id: string;
  tenant_id: string;
  requester_id: string;
  catalog_item_id: string;
  requested_mode: string;
  persistence: 'ephemeral' | 'persistent';
  ttl?: string;
  hardware_profile?: string;
  quota_profile?: string;
  branding_profile_id?: string;
  requested_models?: string[];
  metadata?: Record<string, unknown>;
  status: string;
  created_at: string;
  exposure_policy?: 'internal' | 'public_code';
  public_url?: string;
  one_time_access_code?: string;
}

export interface AvailableModel {
  id: string;
  display_name: string;
  hardware: string;
  use_case: string;
  status: 'healthy';
}

export interface AvailableModelsResponse {
  models: AvailableModel[];
}

export interface ValidationResult {
  validation_id: string;
  session_id: string;
  check_name: string;
  result: 'pass' | 'fail' | 'warn' | 'skipped';
  message?: string;
  evidence?: string;
  timestamp: string;
}

export interface LabSession {
  session_id: string;
  request_id: string;
  tenant_id: string;
  catalog_item_id: string;
  created_at?: string;
  namespace?: string;
  cluster_ref?: string;
  status: string;
  lab_url?: string;
  dashboard_url?: string;
  maas_api_key?: string;
  started_at?: string;
  expires_at?: string;
  completed_at?: string;
  resources: Record<string, unknown>;
  metadata?: Record<string, unknown> & {
    labels?: Record<string, unknown>;
  };
  validation_results: ValidationResult[];
  lifecycle_events: Array<{
    from_status: string;
    to_status: string;
    timestamp: string;
    reason?: string;
  }>;
}

export interface HandoffPackage {
  lab_title: string;
  tenant: string;
  catalog_item: string;
  session_id: string;
  lab_url?: string;
  dashboard_url?: string;
  access_instructions?: string;
  readme?: string;
  expires_at?: string;
  branding_metadata: Record<string, string>;
}

export interface ShowbackRecord {
  showback_id: string;
  tenant_id: string;
  session_id: string;
  catalog_item_id: string;
  namespace?: string;
  duration_seconds: number;
  cpu_requested?: string;
  cpu_used_estimate?: string;
  memory_requested?: string;
  memory_used_estimate?: string;
  model_requests: number;
  estimated_tokens: number;
  gaudi_endpoint_requests: number;
}

export interface RepeatabilityReport {
  session_id: string;
  catalog_item_id: string;
  version: string;
  catalog_versioned: boolean;
  provisioning_plan_generated: boolean;
  validation_passed: boolean;
  handoff_generated: boolean;
  showback_generated: boolean;
  cleanup_defined: boolean;
  repeatability_score: number;
}

export interface WorkshopSeat {
  seat_id: string;
  seat_number: number;
  participant_id?: string;
  status: string;
  session_id?: string;
  lab_url?: string;
  showroom_url?: string;
  error?: string;
}

export interface Workshop {
  workshop_id: string;
  tenant_id: string;
  catalog_item_id: string;
  num_users: number;
  name?: string;
  owner_id?: string;
  ttl: string;
  status: string;
  seats: WorkshopSeat[];
  session_ids: string[];
  cluster_ref?: string;
  target_cluster?: string;
  metadata: Record<string, unknown>;
  exposure_policy?: 'internal' | 'public_code';
  public_url?: string;
  one_time_access_code?: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
}

export interface PublicClaimResult {
  order_id: string;
  seat_ref: string;
  public_url: string;
  participant_id: string;
}

export interface WorkshopCapacityPreview {
  can_provision: boolean;
  reason: string;
  seats_requested: number;
  selected_cluster?: string;
  placement_reason?: string;
  catalog_seat_limit?: number | null;
  certification_override?: boolean;
  certification_target_seats?: number | null;
  estimated_resources: {
    cpu_millicores: number;
    memory_mib: number;
    pods: number;
  };
  resource_breakdown?: {
    shared: WorkshopResourceEstimate;
    per_seat: WorkshopResourceEstimate;
    transient: WorkshopResourceEstimate & { concurrent_seats: number };
  } | null;
}

export interface WorkshopResourceEstimate {
  cpu_millicores: number;
  memory_mib: number;
  pods: number;
}

export type WorkloadType = 'cpu_inference' | 'gpu_inference' | 'training' | 'rag_pipeline' | 'agent' | 'mixed' | 'lightweight';

export interface WorkloadProfile {
  workload_type: WorkloadType;
  compute_intensity: 'low' | 'medium' | 'high';
  memory_intensity: 'low' | 'medium' | 'high';
  gpu_required: boolean;
  gpu_mode: string;
  io_pattern: 'batch' | 'streaming' | 'interactive';
  confidence: number;
  classification_source: string;
}

export interface OrchestrationDecision {
  decision_id: string;
  request_id: string;
  workload_profile?: WorkloadProfile;
  recommended_cluster?: string;
  recommended_hardware: string;
  recommended_quota: string;
  confidence: number;
  rationale: string;
  signals_used: string[];
  fallback_chain: string[];
  decision_timestamp: string;
}

export interface BrandingProfile {
  branding_profile_id: string;
  display_name: string;
  title: string;
  logo_refs?: string[];
  primary_color: string;
  secondary_color: string;
  footer_text?: string;
  theme: string;
  metadata?: Record<string, unknown>;
}

export interface ClusterObservation {
  cluster_id: string;
  cluster_name?: string;
  healthy: boolean;
  eligible: boolean;
  reason?: string;
  available_cpu_millicores: number;
  available_memory_mib: number;
  available_pods: number;
  active_sessions: number;
  active_workshops: number;
  active_seats: number;
  configured_enabled?: boolean;
  inspection_only?: boolean;
}

export interface SeatObservation {
  seat_number: number;
  session_id?: string | null;
  namespace?: string | null;
  status: string;
  started_at?: string | null;
  last_transition_at?: string | null;
  provisioning_seconds?: number | null;
  resolution_state: 'none' | 'attention' | 'resolving' | 'resolved';
  error?: string | null;
  detail_url?: string | null;
}

export interface ProvisioningObservation {
  order_id: string;
  order_type: 'individual' | 'workshop';
  name: string;
  catalog_item_id: string;
  cluster_ref?: string | null;
  status: string;
  started_at?: string | null;
  seats_requested: number;
  ready_seats: number;
  failed_seats: number;
  inflight_seats: number;
  status_counts: Record<string, number>;
  max_ready_seconds?: number | null;
  oldest_inflight_seconds?: number | null;
  seats: SeatObservation[];
  detail_url?: string | null;
}

export interface InflightObservation {
  order_id: string;
  order_type: 'individual' | 'workshop';
  name: string;
  catalog_item_id: string;
  cluster_ref?: string | null;
  inflight_seats: number;
  stage_counts: Record<string, number>;
  oldest_seconds?: number | null;
  detail_url?: string | null;
}

export interface ResolutionObservation {
  order_id: string;
  order_type: 'individual' | 'workshop';
  name: string;
  catalog_item_id: string;
  cluster_ref?: string | null;
  seat_number: number;
  session_id?: string | null;
  status: string;
  state: 'attention' | 'resolving' | 'resolved';
  message?: string | null;
  last_transition_at?: string | null;
  detail_url?: string | null;
}

export interface LlmModelObservation {
  model_id: string;
  display_name: string;
  hardware?: string | null;
  status: string;
  desired_replicas: number;
  ready_replicas: number;
  route: string;
  backend?: string | null;
}

export interface LlmAttributionObservation {
  order_id: string;
  order_type: 'individual' | 'workshop';
  catalog_item_id: string;
  cluster_ref?: string | null;
  seat_number: number;
  session_id: string;
  namespace?: string | null;
  model_id: string;
  requests: number;
  avg_latency_ms?: number | null;
  errors: number;
  rate_limited: number;
  estimated_tokens: number;
}

export interface AdminObservability {
  schema: 'launchpad.admin-observability/v1';
  generated_at: string;
  summary: {
    clusters_healthy: number;
    clusters_total: number;
    labs_active: number;
    seats_active: number;
    seats_inflight: number;
    seats_attention: number;
  };
  clusters: ClusterObservation[];
  provisioning: ProvisioningObservation[];
  inflight: InflightObservation[];
  resolution: ResolutionObservation[];
  grafana: {
    configured: boolean;
    url?: string | null;
    purpose: string;
  };
  llm: {
    summary: {
      models_configured: number;
      models_running: number;
      models_healthy: number;
      requests_observed: number;
      avg_latency_ms?: number | null;
      p95_latency_ms?: number | null;
      errors: number;
      rate_limited: number;
      estimated_tokens: number;
      attributed_requests: number;
    };
    models: LlmModelObservation[];
    attribution: LlmAttributionObservation[];
    telemetry_gaps: string[];
  };
}
