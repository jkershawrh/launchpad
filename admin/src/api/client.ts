import type {
  BrandingProfile,
  CatalogItem,
  ClusterCapacity,
  ClusterPreflightResponse,
  ContainerInfo,
  DetailedSystemHealth,
  FeedbackSummary,
  HandoffPackage,
  HealthAlert,
  LabRequest,
  LabSession,
  OrchestrationDecision,
  RepeatabilityReport,
  SessionDiagnostics,
  ShowbackRecord,
  SystemStatus,
  Tenant,
  AdminObservability,
  LifecycleHealth,
  CatalogIntakeDraft,
  CatalogIntakeSubmission,
  CatalogIntakePipelineView,
  EventRecord,
  EventStatusResult,
  EventAdmissionForecast,
} from './types';

const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  // Tenants
  createTenant: (data: Partial<Tenant>) =>
    request<Tenant>('/tenants', { method: 'POST', body: JSON.stringify(data) }),
  listTenants: () => request<Tenant[]>('/tenants'),
  getTenant: (id: string) => request<Tenant>(`/tenants/${id}`),

  // Catalog
  listCatalog: () => request<CatalogItem[]>('/catalog'),
  getCatalogItem: (id: string) => request<CatalogItem>(`/catalog/${id}`),

  // Lab Requests
  createLabRequest: (data: Partial<LabRequest>) =>
    request<LabRequest>('/lab-requests', { method: 'POST', body: JSON.stringify(data) }),
  listLabRequests: () => request<LabRequest[]>('/lab-requests'),
  getLabRequest: (id: string) => request<LabRequest>(`/lab-requests/${id}`),
  provisionLab: (requestId: string) =>
    request<LabSession>(`/lab-requests/${requestId}/provision`, { method: 'POST' }),

  // Lab Sessions
  listSessions: (limit?: number) => request<LabSession[]>(
    `/lab-sessions?newest_first=true${limit ? `&limit=${limit}` : ''}`,
  ),
  getSession: (id: string) => request<LabSession>(`/lab-sessions/${id}`),
  validateSession: (id: string) =>
    request<LabSession>(`/lab-sessions/${id}/validate`, { method: 'POST' }),
  activateSession: (id: string) =>
    request<LabSession>(`/lab-sessions/${id}/activate`, { method: 'POST' }),
  resetSession: (id: string) =>
    request<LabSession>(`/lab-sessions/${id}/reset`, { method: 'POST' }),
  reclaimSession: (id: string) =>
    request<LabSession>(`/lab-sessions/${id}/reclaim`, { method: 'POST' }),

  // Reports
  getHandoff: (id: string) => request<HandoffPackage>(`/lab-sessions/${id}/handoff`),
  getShowback: (id: string) => request<ShowbackRecord>(`/lab-sessions/${id}/showback`),
  getRepeatabilityReport: (id: string) =>
    request<RepeatabilityReport>(`/lab-sessions/${id}/repeatability-report`),

  // Branding
  listBrandingProfiles: () => request<BrandingProfile[]>('/branding-profiles'),
  getBrandingProfile: (id: string) => request<BrandingProfile>(`/branding-profiles/${id}`),

  // Admin
  getSystemStatus: () => request<SystemStatus>('/admin/system/status'),
  getDetailedSystemHealth: () => request<DetailedSystemHealth>('/admin/system/health'),
  getClusterPreflight: () => request<ClusterPreflightResponse>('/admin/clusters/preflight'),
  getAdminObservability: () => request<AdminObservability>('/admin/observability'),
  getLifecycleHealth: () => request<LifecycleHealth>('/admin/lifecycle'),
  listContainers: () => request<ContainerInfo[]>('/admin/system/containers'),
  restartContainer: (name: string) =>
    request<{ success: boolean }>(`/admin/system/containers/${name}/restart`, { method: 'POST' }),
  forceReclaimSession: (id: string) =>
    request<LabSession>(`/admin/sessions/${id}/force-reclaim`, { method: 'POST' }),
  forceReclaimCatalog: (catalogItemId: string) =>
    request<import('./types').CatalogReclaimResult>(
      `/admin/catalog/${encodeURIComponent(catalogItemId)}/force-reclaim`,
      { method: 'POST' },
    ),
  getSessionDiagnostics: (id: string) =>
    request<SessionDiagnostics>(`/admin/sessions/${id}/diagnostics`),
  addCatalogItem: (data: Partial<CatalogItem>) =>
    request<CatalogItem>('/admin/catalog', { method: 'POST', body: JSON.stringify(data) }),
  updateCatalogItem: (id: string, data: Partial<CatalogItem>) =>
    request<CatalogItem>(`/admin/catalog/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  setCatalogStatus: (id: string, status: string) =>
    request<CatalogItem>(`/admin/catalog/${id}/status`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  listCatalogIntakes: () =>
    request<CatalogIntakeDraft[]>('/admin/catalog-intakes'),
  getCatalogIntake: (id: string) =>
    request<CatalogIntakeDraft>(`/admin/catalog-intakes/${encodeURIComponent(id)}`),
  getCatalogIntakePipeline: (id: string) =>
    request<CatalogIntakePipelineView>(`/admin/catalog-intakes/${encodeURIComponent(id)}/pipeline`),
  submitCatalogIntake: (data: CatalogIntakeSubmission) =>
    request<CatalogIntakeDraft>('/admin/catalog-intakes', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  approveCatalogIntakeSource: (id: string) =>
    request<CatalogIntakeDraft>(`/admin/catalog-intakes/${encodeURIComponent(id)}/source-approval`, { method: 'POST' }),
  runCatalogIntakeDiscovery: (id: string) =>
    request<CatalogIntakeDraft>(`/admin/catalog-intakes/${encodeURIComponent(id)}/discovery`, { method: 'POST' }),

  // Approved event demand (read-only admin visibility)
  listEvents: () => request<EventRecord[]>('/events'),
  getEvent: (id: string) => request<EventRecord>(`/events/${encodeURIComponent(id)}`),
  getEventStatus: (id: string) => request<EventStatusResult>(`/events/${encodeURIComponent(id)}/status`),
  getEventAdmissionForecast: (id: string) => request<EventAdmissionForecast>(`/events/${encodeURIComponent(id)}/admission-forecast`),

  // Intelligence / Feedback
  getFeedbackSummary: () =>
    request<{ summaries: FeedbackSummary[] }>('/admin/feedback/summary'),
  getFeedbackByCluster: (clusterName: string) =>
    request<{ summaries: FeedbackSummary[] }>(`/admin/feedback/cluster/${clusterName}`),
  getFleetHealth: () =>
    request<{ clusters: ClusterCapacity[]; alerts: HealthAlert[] }>('/intelligence/fleet-health'),
  getDecision: (requestId: string) =>
    request<OrchestrationDecision>(`/intelligence/decision/${requestId}`),
};
