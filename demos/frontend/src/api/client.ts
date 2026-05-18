const API_BASE = import.meta.env.VITE_API_URL || '';
const AUTH_TOKEN = import.meta.env.VITE_AUTH_TOKEN || '';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    ...(options?.body ? { 'Content-Type': 'application/json' } : {}),
    ...(AUTH_TOKEN ? { 'X-API-Key': AUTH_TOKEN } : {}),
    ...(options?.headers as Record<string, string> || {}),
  };
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: 'same-origin',
  });
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

export const api = {
  getHealth: () => request<import('./types').HealthStatus>('/health'),

  getBackends: () => request<{ backends: import('./types').BackendInfo[] }>('/v1/backends'),
  getRoutes: () => request<{ routes: import('./types').Route[] }>('/v1/routes'),

  routeRequest: (body: Record<string, unknown>, signal?: AbortSignal) =>
    request<import('./types').RouteResponse>('/v1/route', {
      method: 'POST',
      body: JSON.stringify(body),
      signal,
    }),

  getRequests: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return request<import('./types').PaginatedResponse<import('./types').InferenceRequest>>(`/api/v1/requests${qs}`);
  },

  getDecisions: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return request<import('./types').PaginatedResponse<import('./types').GovernanceDecision>>(`/api/v1/decisions${qs}`);
  },

  approveDecision: (id: string, approvedBy: string) =>
    request<{ status: string }>(`/api/v1/decisions/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: approvedBy }),
    }),

  getRoutingRules: () => request<{ data: import('./types').RoutingRule[] }>('/api/v1/routing-rules'),

  getCostSummary: (days = 30) =>
    request<import('./types').AnalyticsResponse<import('./types').CostSummaryItem>>(`/api/v1/cost-summary?days=${days}`),

  getRoutingDistribution: (days = 7) =>
    request<import('./types').AnalyticsResponse<import('./types').RoutingDistribution>>(`/api/v1/analytics/routing-distribution?days=${days}`),

  getLatencyPercentiles: (days = 7) =>
    request<import('./types').AnalyticsResponse<import('./types').LatencyPercentiles>>(`/api/v1/analytics/latency-percentiles?days=${days}`),

  getCostByTask: (days = 30) =>
    request<import('./types').AnalyticsResponse<import('./types').CostSummaryItem>>(`/api/v1/analytics/cost-by-task?days=${days}`),

  getGovernanceSummary: (days = 30) =>
    request<import('./types').AnalyticsResponse<import('./types').GovernanceSummaryItem>>(`/api/v1/analytics/governance-summary?days=${days}`),

  overdriveRoute: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>('/v1/overdrive/route', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  overdriveBatch: (requests: Record<string, unknown>[]) =>
    request<Record<string, unknown>>('/v1/overdrive/batch', {
      method: 'POST',
      body: JSON.stringify({ requests }),
    }),

  overdriveStatus: () =>
    request<Record<string, unknown>>('/v1/overdrive/status'),

  overdriveSetHealth: (lane: string, healthy: boolean) =>
    request<Record<string, unknown>>(`/v1/overdrive/health/${lane}?healthy=${healthy}`, {
      method: 'POST',
    }),

  tokenize: (text: string, mode: 'approximate' | 'real' = 'approximate') =>
    request<Record<string, unknown>>('/v1/tokenize', {
      method: 'POST',
      body: JSON.stringify({ text, mode }),
    }),

  workloadProfiles: () =>
    request<Record<string, unknown>>('/v1/workload/profiles'),

  workloadRun: (profile: string, mode: string, seed: number, live = false, unlock_code = '') =>
    request<Record<string, unknown>>('/v1/workload/run', {
      method: 'POST',
      body: JSON.stringify({ profile, mode, seed, live, unlock_code }),
    }),

  workloadStatus: (runId: string) =>
    request<Record<string, unknown>>(`/v1/workload/status/${runId}`),

  agentResearch: (question: string, governance_mode: string, live = false) =>
    request<Record<string, unknown>>('/v1/agent/research', {
      method: 'POST',
      body: JSON.stringify({ question, governance_mode, live }),
    }),

  agentStatus: (runId: string) =>
    request<Record<string, unknown>>(`/v1/agent/status/${runId}`),

  agentApprove: (runId: string, stepName: string) =>
    request<Record<string, unknown>>(`/v1/agent/approve/${runId}/${stepName}`, {
      method: 'POST',
    }),

  trainingProfiles: () =>
    request<Record<string, unknown>>('/v1/training/profiles'),

  trainingRun: (task: string, model: string, dataset: string, mode: string, seed: number) =>
    request<Record<string, unknown>>('/v1/training/run', {
      method: 'POST',
      body: JSON.stringify({ task, model, dataset, mode, seed }),
    }),

  trainingStatus: (runId: string) =>
    request<Record<string, unknown>>(`/v1/training/status/${runId}`),

  platformStatus: () =>
    request<Record<string, unknown>>('/v1/platform/status'),

  swarmRun: (scenario: string, seed: number, depth: string = 'full') =>
    request<Record<string, unknown>>('/v1/swarm/run', { method: 'POST', body: JSON.stringify({ scenario, seed, depth }) }),

  swarmStatus: (runId: string) =>
    request<Record<string, unknown>>(`/v1/swarm/status/${runId}`),

  replayCompare: (profile: string, seed: number) =>
    request<Record<string, unknown>>('/v1/replay/compare', { method: 'POST', body: JSON.stringify({ profile, seed }) }),

  recoveryRun: (seed: number) =>
    request<Record<string, unknown>>('/v1/recovery/run', { method: 'POST', body: JSON.stringify({ seed }) }),

  listTenants: () =>
    request<Record<string, unknown>>('/api/v1/tenants'),

  createTenant: (slug: string, display_name: string, tier: string = 'pilot') =>
    request<Record<string, unknown>>('/api/v1/tenants', { method: 'POST', body: JSON.stringify({ slug, display_name, tier }) }),

  getTenant: (slug: string) =>
    request<Record<string, unknown>>(`/api/v1/tenants/${slug}`),

  capacityOverview: () =>
    request<Record<string, unknown>>('/v1/capacity/overview'),

  runHistory: (runType?: string) => {
    const qs = runType ? `?run_type=${runType}` : '';
    return request<Record<string, unknown>>(`/v1/runs/history${qs}`);
  },

  validateContent: (name: string, type: string, source: string) =>
    request<Record<string, unknown>>('/v1/content/validate', { method: 'POST', body: JSON.stringify({ name, type, source }) }),

  galleryPocs: (category?: string) => {
    const qs = category ? `?category=${category}` : '';
    return request<Record<string, unknown>>(`/v1/gallery/pocs${qs}`);
  },
};
