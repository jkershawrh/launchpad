import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AppLayout from './components/AppLayout';
import ErrorBoundary from './components/ErrorBoundary';
import Overview from './pages/Overview';
import Architecture from './pages/Architecture';
import TryIt from './pages/TryIt';
import Operations from './pages/Operations';
import GovernanceAudit from './pages/GovernanceAudit';
import Overdrive from './pages/Overdrive';
import Docs from './pages/Docs';
import Tokenizer from './pages/Tokenizer';
import WorkloadDemo from './pages/WorkloadDemo';
import ResearchAgent from './pages/ResearchAgent';
import TrainingDemo from './pages/TrainingDemo';
import OptimizationDemo from './pages/OptimizationDemo';
import SwarmDemo from './pages/SwarmDemo';
import ReplayDemo from './pages/ReplayDemo';
import RecoveryDemo from './pages/RecoveryDemo';
import CockpitDashboard from './pages/CockpitDashboard';
import FleetIntelligence from './pages/FleetIntelligence';
import TenantAdmin from './pages/TenantAdmin';
import CapacityDashboard from './pages/CapacityDashboard';
import PublishingHouse from './pages/PublishingHouse';
import { TenantProvider } from './context/TenantContext';
import { LaunchpadConfigProvider, useConfig, isPageEnabled } from './context/LaunchpadConfig';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30000 },
  },
});

function AppRoutes() {
  const config = useConfig();
  const enabled = (page: string) => isPageEnabled(config, page);

  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Overview />} />
        {enabled('architecture') && <Route path="/architecture" element={<Architecture />} />}
        {enabled('try-it') && <Route path="/try-it" element={<TryIt />} />}
        {enabled('operations') && <Route path="/operations" element={<Operations />} />}
        {enabled('governance') && <Route path="/governance" element={<GovernanceAudit />} />}
        {enabled('overdrive') && <Route path="/overdrive" element={<Overdrive />} />}
        {enabled('tokenizer') && <Route path="/tokenizer" element={<Tokenizer />} />}
        {enabled('workload') && <Route path="/workload" element={<WorkloadDemo />} />}
        {enabled('agent') && <Route path="/agent" element={<ResearchAgent />} />}
        {enabled('training') && <Route path="/training" element={<TrainingDemo />} />}
        {enabled('optimization') && <Route path="/optimization" element={<OptimizationDemo />} />}
        {enabled('swarm') && <Route path="/swarm" element={<SwarmDemo />} />}
        {enabled('replay') && <Route path="/replay" element={<ReplayDemo />} />}
        {enabled('recovery') && <Route path="/recovery" element={<RecoveryDemo />} />}
        {enabled('cockpit') && <Route path="/cockpit" element={<CockpitDashboard />} />}
        {enabled('fleet-intel') && <Route path="/fleet-intel" element={<FleetIntelligence />} />}
        {enabled('capacity') && <Route path="/capacity" element={<CapacityDashboard />} />}
        {enabled('gallery') && <Route path="/gallery" element={<PublishingHouse />} />}
        {enabled('admin') && <Route path="/admin/tenants" element={<TenantAdmin />} />}
        {enabled('docs') && <Route path="/docs" element={<Docs />} />}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
    <TenantProvider>
    <LaunchpadConfigProvider>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
    </LaunchpadConfigProvider>
    </TenantProvider>
    </ErrorBoundary>
  );
}
