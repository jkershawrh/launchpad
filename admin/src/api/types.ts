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
  status: string;
  created_at: string;
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

export interface BrandingProfile {
  branding_profile_id: string;
  display_name: string;
  title: string;
  primary_color: string;
  secondary_color: string;
  footer_text?: string;
  theme: string;
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

export interface OrchestrationDecision {
  decision_id: string;
  request_id: string;
  workload_profile?: {
    workload_type: string;
    compute_intensity: string;
    memory_intensity: string;
    gpu_required: boolean;
    confidence: number;
  };
  recommended_cluster?: string;
  recommended_hardware: string;
  recommended_quota: string;
  confidence: number;
  rationale: string;
  signals_used: string[];
  fallback_chain: string[];
  decision_timestamp: string;
}

export interface ClusterCapacity {
  cluster_id?: string;
  cluster_name: string;
  score?: number;
  cpu_utilization?: number;
  gpu_available?: boolean;
  health_status: string;
  healthy?: boolean;
  eligible?: boolean;
  reason?: string;
  configured_enabled?: boolean;
  inspection_only?: boolean;
  available_cpu_millicores?: number;
  available_memory_mib?: number;
  available_pods?: number;
  active_sessions?: number;
  active_workshops?: number;
  active_seats?: number;
  capabilities?: string[];
  ingress_domain?: string;
  last_updated?: string;
}

export interface DetailedHealthCheck {
  status: string;
  [key: string]: string | number | boolean | undefined;
}

export interface DetailedSystemHealth {
  status: string;
  checks: Record<string, DetailedHealthCheck>;
  timestamp: string;
  uptime_seconds: number;
}

export interface ClusterPreflightResponse {
  mutates_cluster: false;
  clusters: ClusterCapacity[];
}

export interface HealthAlert {
  alert_id: string;
  cluster_name: string;
  alert_type: string;
  severity: 'info' | 'warning' | 'critical';
  recommended_action: string;
  created_at: string;
}

export interface ContainerInfo {
  name: string;
  image: string;
  status: string;
  ports: string;
  uptime: string;
  cpu_percent: string;
  memory_usage: string;
  memory_percent: string;
  id: string;
}

export interface SeatResourceUsage { available: boolean; reason?: string | null; cpu_millicores?: number | null; memory_mib?: number | null; pod_count?: number | null; ready_pods?: number | null; restarts?: number | null; terminal_reconnects?: number | null; observed_at?: string | null }
export interface SeatObservation { seat_number: number; session_id?: string | null; namespace?: string | null; status: string; provisioning_seconds?: number | null; resolution_state: string; error?: string | null; detail_url?: string | null; resource_usage?: SeatResourceUsage }
export interface ProvisioningObservation { order_id: string; order_type: string; name: string; catalog_item_id: string; cluster_ref?: string | null; status: string; seats_requested: number; ready_seats: number; failed_seats: number; inflight_seats: number; status_counts: Record<string, number>; max_ready_seconds?: number | null; oldest_inflight_seconds?: number | null; seats: SeatObservation[]; detail_url?: string | null }
export interface LlmAttributionObservation { order_id: string; catalog_item_id: string; cluster_ref?: string | null; seat_number: number; session_id: string; namespace?: string | null; model_id: string; requests: number; avg_latency_ms?: number | null; p95_latency_ms?: number | null; errors: number; rate_limited: number; total_tokens: number }
export interface AdminObservability {
  schema: string; generated_at: string;
  summary: { clusters_healthy: number; clusters_total: number; labs_active: number; seats_active: number; seats_inflight: number; seats_attention: number };
  clusters: Array<{ cluster_id: string; cluster_name?: string; healthy: boolean; eligible: boolean; reason?: string; available_cpu_millicores: number; available_memory_mib: number; available_pods: number; active_sessions: number; active_workshops: number; active_seats: number }>;
  provisioning: ProvisioningObservation[];
  inflight: Array<{ order_id: string; name: string; cluster_ref?: string | null; inflight_seats: number; stage_counts: Record<string, number>; oldest_seconds?: number | null }>;
  resolution: Array<{ order_id: string; name: string; cluster_ref?: string | null; seat_number: number; session_id?: string | null; status: string; state: string; message?: string | null; detail_url?: string | null }>;
  grafana: { configured: boolean; url?: string | null; purpose: string };
  llm: { summary: { models_configured: number; models_running: number; models_healthy: number; requests_observed: number; avg_latency_ms?: number | null; p95_latency_ms?: number | null; errors: number; rate_limited: number; total_tokens: number; attributed_requests: number }; models: Array<{ model_id: string; display_name: string; hardware?: string | null; status: string; desired_replicas: number; ready_replicas: number; route: string; backend?: string | null }>; attribution: LlmAttributionObservation[]; telemetry_gaps: string[] };
}
export interface LifecycleHealth { enabled: boolean; summary: { queued: number; running: number; failed: number; takeovers: number; reclaim_pending: number }; jobs: Array<{ job_id: string; operation: string; cluster_ref?: string | null; status: string; attempts: number; max_attempts: number; last_error?: string | null }> }

export interface SystemStatus {
  containers: number;
  active_sessions: number;
  healthy: boolean;
  containers_list: Array<{ name: string; status: string; ports: string; uptime: string }>;
}

export interface ContainerLogs {
  name: string;
  logs: string;
}

export interface SessionDiagnostics {
  session_id: string;
  container_status: Array<Record<string, unknown>>;
  health_checks: Array<Record<string, unknown>>;
  recent_logs: string;
}

export interface CatalogReclaimResult {
  catalog_item_id: string;
  requested_count: number;
  reclaimed_count: number;
  failed_count: number;
  results: Array<{
    session_id: string;
    status: string;
    error?: string;
  }>;
}

export type CatalogIntakeLabType = 'quick_start' | 'guided_build' | 'open_sandbox';

export interface CatalogIntakeSubmission {
  catalog_item_id: string;
  display_name: string;
  repository_url: string;
  revision: string;
  owner: string;
  audience: string[];
  duration_hours: number;
  lab_type: CatalogIntakeLabType;
  expected_scale: number;
}

export interface CatalogIntakeQualityArtifact {
  path: string;
  status: 'present' | 'present-valid' | 'missing' | 'invalid';
  entry_count?: number;
}

export interface CatalogIntakeQualityProfile {
  schema_version: 'launchpad.redhat.com/catalog-intake-quality/v1';
  business_solution: {
    status: 'review-required';
    readme_present: boolean;
    title: string;
    action_oriented_title: boolean;
    required_sections_present: boolean;
    missing_sections: string[];
    business_language_present: boolean;
    human_review_required: true;
  };
  artifacts: Record<string, CatalogIntakeQualityArtifact>;
  showroom: {
    page_count: number;
    hands_on_module_count: number;
    execute_block_count: number;
    see_section_count: number;
    verification_section_count: number;
    key_takeaway_count: number;
    thin_modules: string[];
  };
  capacity_proposal: {
    status: 'review-required';
    inference_mode: 'local-model' | 'remote-endpoint' | 'unknown';
    framework_signals: string[];
    declared_models: unknown[];
    explicit_resource_envelopes: number;
    measurement_required_before_placement: true;
  };
  security_summary: {
    status: 'review-required';
    mutable_image_count: number;
    cluster_scoped_resource_count: number;
    privileged_finding_count: number;
    secret_manifest_count: number;
    unparsed_manifest_count: number;
    secret_values_included: false;
  };
  portfolio_overlap: {
    status: 'not-run';
    reason: string;
    mutable_live_org_scan_allowed: false;
  };
  gate: {
    status: 'blocked' | 'review-required';
    blocking_findings: string[];
  };
  authority: {
    mode: 'analysis-only';
    may_modify_source: false;
    may_publish_catalog: false;
    may_provision: false;
    may_certify: false;
  };
}

export interface CatalogIntakeDraft {
  intake_id: string;
  state: 'draft';
  orderable: false;
  promotion_eligible: false;
  storage_scope: 'process-local-draft' | 'durable-postgres';
  requested: CatalogIntakeSubmission;
  defaults: { exposure_policies: string[]; maximum_seats: number };
  blockers: string[];
  evidence: {
    status: 'not-run' | 'partial';
    artifacts: string[];
    required_gates: string[];
  };
  supported_targets: string[];
  target_status: 'unverified';
  release_identity: { repository_url: string; revision: string };
  approval_history: Array<Record<string, string>>;
  rollback: { status: 'not-defined'; metadata: Record<string, string> };
  discovery?: {
    status: 'passed';
    attempt_id: string;
    output_hash: string;
    worker_image_digest: string;
    files_scanned: number;
    bytes_scanned: number;
    cleanup_verified: true;
  } | null;
  catalog_preview?: {
    catalog_item_id: string;
    display_name: string;
    description: string;
    category: CatalogIntakeLabType;
    version: string;
    status: 'draft';
    required_capabilities: string[];
    optional_capabilities: string[];
    metadata: Record<string, unknown> & {
      intake_quality?: CatalogIntakeQualityProfile;
    };
  } | null;
  source_approval?: {
    approval_id: string;
    repository_url: string;
    revision: string;
    requested_by: string;
    approved_by: string;
    approved_at: string;
    expires_at: string;
    purpose: string;
  } | null;
  discovery_execution?: {
    attempt_id: string;
    state: 'queued' | 'running' | 'failed';
    requested_by: string;
    requested_at: string;
    error_codes: string[];
  } | null;
}

export interface CatalogIntakePipelineView {
  schema_version: 'launchpad.redhat.com/catalog-intake-pipeline/v1';
  intake_id: string;
  source_standard: 'quickstart-repository';
  metadata_policy: 'discover-from-source';
  current_stage: 'submitted' | 'draft-generated';
  orderable: false;
  promotion_eligible: false;
  durable_storage: boolean;
  isolated_worker_available: boolean;
  stages: Array<{
    stage_id: string;
    label: string;
    status: 'current' | 'locked' | 'complete';
    gate_ids: string[];
  }>;
  gates: Array<{
    gate_id: string;
    label: string;
    status: 'blocked' | 'not-run' | 'passed' | 'failed';
    required_evidence: string[];
    blockers: string[];
  }>;
  actions: {
    approve_source: boolean;
    run_discovery: boolean;
    generate_draft: boolean;
    run_one_seat_certification: boolean;
    request_review: boolean;
    promote: boolean;
  };
}

export interface EventResourceVector {
  seats: number;
  cpu_millicores: number;
  memory_mib: number;
  pods: number;
  storage_gib: number;
  routes: number;
  model_slots: number;
}

export interface EventCohort {
  cohort_id: string;
  participants: number;
  lab_refs: string[];
  starts_at?: string | null;
}

export interface EventLab {
  lab_ref: string;
  catalog_id: string;
  catalog_release: string;
  required_capabilities: string[];
}

export interface EventManifest {
  event_id: string;
  name: string;
  owner: string;
  technical_approver: string;
  exposure_policy: 'internal' | 'public_code';
  placement_policy: 'single_cluster_per_workshop';
  cohorts: EventCohort[];
  labs: EventLab[];
  retention: { hours: number; starts_from: 'event_start' | 'cohort_start' | 'claim' };
  approval: {
    event_owner_approved: boolean;
    technical_approver_approved: boolean;
    approved_seat_environments: number;
    approved_retention_hours: number;
    approved_at?: string | null;
  };
}

export interface EventCapacityPreview {
  matrix_id: string;
  matrix_digest: string;
  fleet_snapshot_id: string;
  fleet_observed_at?: string | null;
  participant_count: number;
  seat_environments: number;
  peak_concurrent_participants: number;
  peak_retained_environments: number;
  certified_capacity: number;
  dr_reserved_capacity: number;
  uncertified_capacity: number;
  capacity_shortfall: number;
  eligible: boolean;
  explanation: string;
  allocations: Array<{
    cohort_id: string;
    lab_ref: string;
    catalog_id: string;
    catalog_release: string;
    cluster_id: string;
    seats: number;
  }>;
  lab_capacity: Array<{
    lab_ref: string;
    catalog_id: string;
    catalog_release: string;
    required_seats: number;
    allocated_seats: number;
    shortfall: number;
  }>;
}

export interface EventRecord {
  manifest: EventManifest;
  capacity_preview: EventCapacityPreview;
  created_at: string;
}

export interface EventWorkshopStatusItem {
  reservation_id: string;
  cohort_id: string;
  lab_ref: string;
  catalog_id: string;
  catalog_release: string;
  cluster_ref: string;
  seats: number;
  reservation_status: 'held' | 'consumed' | 'released' | 'expired';
  workshop_id?: string | null;
  workshop_status?: string | null;
  lifecycle_job_id?: string | null;
  lifecycle_job_status?: string | null;
  ready_seats: number;
  failed_seats: number;
  reclaimed_seats: number;
  public_access_state: 'not_required' | 'pending_activation' | 'active' | 'disabled';
  public_url?: string | null;
}

export interface EventStatusResult {
  event_id: string;
  state: 'approved' | 'reserved' | 'progressing' | 'awaiting_public_access' | 'ready' | 'cleanup_evidence_pending' | 'released' | 'attention_required';
  reservation_complete: boolean;
  summary: {
    reservations: number;
    workshops: number;
    lifecycle_jobs: number;
    seats: number;
    ready_seats: number;
    failed_seats: number;
    reclaimed_seats: number;
    public_workshops_active: number;
  };
  workshops: EventWorkshopStatusItem[];
  observed_at: string;
}
