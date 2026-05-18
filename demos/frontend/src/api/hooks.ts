import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from './client';

export function useHealth() {
  return useQuery({ queryKey: ['health'], queryFn: api.getHealth, refetchInterval: 30000 });
}

export function useBackends() {
  return useQuery({ queryKey: ['backends'], queryFn: api.getBackends, retry: 3, retryDelay: 2000 });
}

export function useRoutes() {
  return useQuery({ queryKey: ['routes'], queryFn: api.getRoutes, retry: 3, retryDelay: 2000 });
}

export function useRequests(params?: Record<string, string>) {
  return useQuery({ queryKey: ['requests', params], queryFn: () => api.getRequests(params) });
}

export function useDecisions(params?: Record<string, string>) {
  return useQuery({ queryKey: ['decisions', params], queryFn: () => api.getDecisions(params) });
}

export function useRoutingRules() {
  return useQuery({ queryKey: ['routing-rules'], queryFn: api.getRoutingRules });
}

export function useCostSummary(days = 30) {
  return useQuery({ queryKey: ['cost-summary', days], queryFn: () => api.getCostSummary(days) });
}

export function useRoutingDistribution(days = 7) {
  return useQuery({ queryKey: ['routing-distribution', days], queryFn: () => api.getRoutingDistribution(days) });
}

export function useLatencyPercentiles(days = 7) {
  return useQuery({ queryKey: ['latency-percentiles', days], queryFn: () => api.getLatencyPercentiles(days) });
}

export function useCostByTask(days = 30) {
  return useQuery({ queryKey: ['cost-by-task', days], queryFn: () => api.getCostByTask(days) });
}

export function useGovernanceSummary(days = 30) {
  return useQuery({ queryKey: ['governance-summary', days], queryFn: () => api.getGovernanceSummary(days) });
}

export function useApproveDecision() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, approvedBy }: { id: string; approvedBy: string }) =>
      api.approveDecision(id, approvedBy),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['decisions'] });
      queryClient.invalidateQueries({ queryKey: ['governance-summary'] });
    },
  });
}

export function useRouteRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.routeRequest(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['requests'] });
    },
  });
}
