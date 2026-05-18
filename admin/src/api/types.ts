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
