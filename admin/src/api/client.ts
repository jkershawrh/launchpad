import type {
  BrandingProfile,
  CatalogItem,
  ContainerInfo,
  ContainerLogs,
  HandoffPackage,
  LabRequest,
  LabSession,
  RepeatabilityReport,
  SessionDiagnostics,
  ShowbackRecord,
  SystemStatus,
  Tenant,
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
  listSessions: () => request<LabSession[]>('/lab-sessions'),
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
  listContainers: () => request<ContainerInfo[]>('/admin/system/containers'),
  getContainerLogs: (name: string, lines?: number) =>
    request<ContainerLogs>(`/admin/system/containers/${name}/logs?lines=${lines || 100}`),
  restartContainer: (name: string) =>
    request<{ success: boolean }>(`/admin/system/containers/${name}/restart`, { method: 'POST' }),
  forceReclaimSession: (id: string) =>
    request<LabSession>(`/admin/sessions/${id}/force-reclaim`, { method: 'POST' }),
  getSessionDiagnostics: (id: string) =>
    request<SessionDiagnostics>(`/admin/sessions/${id}/diagnostics`),
  addCatalogItem: (data: Partial<CatalogItem>) =>
    request<CatalogItem>('/admin/catalog', { method: 'POST', body: JSON.stringify(data) }),
  updateCatalogItem: (id: string, data: Partial<CatalogItem>) =>
    request<CatalogItem>(`/admin/catalog/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  setCatalogStatus: (id: string, status: string) =>
    request<CatalogItem>(`/admin/catalog/${id}/status`, { method: 'PATCH', body: JSON.stringify({ status }) }),
};
