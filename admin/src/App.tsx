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
          <Route path="/reports" element={<Reports />} />
          <Route path="/analytics" element={<ProvisioningAnalytics />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
