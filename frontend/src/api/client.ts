import type {
  BrandingProfile,
  CatalogItem,
  HandoffPackage,
  LabRequest,
  LabSession,
  OrchestrationDecision,
  RepeatabilityReport,
  ShowbackRecord,
  Tenant,
  Workshop,
  WorkshopCapacityPreview,
} from './types';

const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
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

  // Intelligence
  getDecision: (requestId: string) =>
    request<OrchestrationDecision>(`/intelligence/decision/${requestId}`),

  // Workshops
  previewWorkshop: (data: Record<string, unknown>) =>
    request<WorkshopCapacityPreview>('/workshops/capacity-preview', {
      method: 'POST', body: JSON.stringify(data),
    }),
  createWorkshopOrder: (data: Record<string, unknown>, idempotencyKey: string) =>
    request<Workshop>('/workshops/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(data),
    }),
  confirmWorkshop: (id: string) =>
    request<Workshop>(`/workshops/${id}/confirm`, { method: 'POST' }),
  listWorkshops: () => request<Workshop[]>('/workshops'),
  getWorkshop: (id: string) => request<Workshop>(`/workshops/${id}`),
  reclaimWorkshop: (id: string) =>
    request<Workshop>(`/workshops/${id}`, { method: 'DELETE' }),
};
