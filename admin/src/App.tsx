import { BrowserRouter, Route, Routes } from 'react-router-dom';
import AdminLayout from './components/AdminLayout';
import CatalogManagement from './pages/CatalogManagement';
import Dashboard from './pages/Dashboard';
import ProvisioningAnalytics from './pages/ProvisioningAnalytics';
import Reports from './pages/Reports';
import SessionDetail from './pages/SessionDetail';
import Sessions from './pages/Sessions';
import SystemStatus from './pages/SystemStatus';
import Tenants from './pages/Tenants';
import Observability from './pages/Observability';
import CatalogIntakes from './pages/CatalogIntakes';
import CatalogIntakeDetail from './pages/CatalogIntakeDetail';
import NewCatalogIntake from './pages/NewCatalogIntake';
import Events from './pages/Events';
import EventDetail from './pages/EventDetail';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AdminLayout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/sessions" element={<Sessions />} />
          <Route path="/sessions/:sessionId" element={<SessionDetail />} />
          <Route path="/tenants" element={<Tenants />} />
          <Route path="/system" element={<SystemStatus />} />
          <Route path="/catalog" element={<CatalogManagement />} />
          <Route path="/intakes" element={<CatalogIntakes />} />
          <Route path="/intakes/new" element={<NewCatalogIntake />} />
          <Route path="/intakes/:intakeId" element={<CatalogIntakeDetail />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/analytics" element={<ProvisioningAnalytics />} />
          <Route path="/observability" element={<Observability />} />
          <Route path="/events" element={<Events />} />
          <Route path="/events/:eventId" element={<EventDetail />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
