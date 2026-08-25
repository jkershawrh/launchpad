import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import { BrandingProvider } from './context/BrandingContext';
import Overview from './pages/Overview';
import Decisions from './pages/Decisions';
import Fleet from './pages/Fleet';
import Workloads from './pages/Workloads';
import Feedback from './pages/Feedback';
import Timing from './pages/Timing';
import Catalog from './pages/Catalog';
import Demos from './pages/Demos';
import Sandbox from './pages/Sandbox';
import SessionDetail from './pages/SessionDetail';
import PortalDashboard from './pages/PortalDashboard';
import Sessions from './pages/Sessions';
import LabRequestForm from './pages/LabRequestForm';
import Admin from './pages/Admin';
import WorkshopOrderForm from './pages/WorkshopOrderForm';
import { getAppSurface } from './appSurface';

export default function App() {
  const surface = getAppSurface(
    window.location.hostname,
    new URLSearchParams(window.location.search).get('surface'),
  );

  return (
    <BrowserRouter>
      <BrandingProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={surface === 'operations' ? <Overview /> : <PortalDashboard />} />
            {surface === 'operations' ? (
              <>
                <Route path="/decisions" element={<Decisions />} />
                <Route path="/fleet" element={<Fleet />} />
                <Route path="/workloads" element={<Workloads />} />
                <Route path="/feedback" element={<Feedback />} />
                <Route path="/timing" element={<Timing />} />
                <Route path="/admin" element={<Admin />} />
              </>
            ) : (
              <>
                <Route path="/catalog" element={<Catalog />} />
                <Route path="/demos" element={<Demos />} />
                <Route path="/sandbox" element={<Sandbox />} />
                <Route path="/request" element={<LabRequestForm />} />
                <Route path="/workshops/new" element={<WorkshopOrderForm />} />
                <Route path="/sessions" element={<Sessions />} />
              </>
            )}
            <Route path="/sessions/:sessionId" element={<SessionDetail />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrandingProvider>
    </BrowserRouter>
  );
}
