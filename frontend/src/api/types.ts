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
  metadata?: Record<string, unknown>;
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
  metadata: Record<string, unknown>;
}

export interface WorkshopCapacityPreview {
  can_provision: boolean;
  reason: string;
  seats_requested: number;
  estimated_resources: {
    cpu_millicores: number;
    memory_mib: number;
  };
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
