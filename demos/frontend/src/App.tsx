import { BrowserRouter, Routes, Route } from 'react-router-dom';
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
import TenantAdmin from './pages/TenantAdmin';
import CapacityDashboard from './pages/CapacityDashboard';
import PublishingHouse from './pages/PublishingHouse';
import { TenantProvider } from './context/TenantContext';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30000 },
  },
});

export default function App() {
  return (
    <ErrorBoundary>
    <TenantProvider>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<Overview />} />
            <Route path="/architecture" element={<Architecture />} />
            <Route path="/try-it" element={<TryIt />} />
            <Route path="/operations" element={<Operations />} />
            <Route path="/governance" element={<GovernanceAudit />} />
            <Route path="/overdrive" element={<Overdrive />} />
            <Route path="/tokenizer" element={<Tokenizer />} />
            <Route path="/workload" element={<WorkloadDemo />} />
            <Route path="/agent" element={<ResearchAgent />} />
            <Route path="/training" element={<TrainingDemo />} />
            <Route path="/optimization" element={<OptimizationDemo />} />
            <Route path="/swarm" element={<SwarmDemo />} />
            <Route path="/replay" element={<ReplayDemo />} />
            <Route path="/recovery" element={<RecoveryDemo />} />
            <Route path="/cockpit" element={<CockpitDashboard />} />
            <Route path="/capacity" element={<CapacityDashboard />} />
            <Route path="/gallery" element={<PublishingHouse />} />
            <Route path="/admin/tenants" element={<TenantAdmin />} />
            <Route path="/docs" element={<Docs />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
    </TenantProvider>
    </ErrorBoundary>
  );
}
