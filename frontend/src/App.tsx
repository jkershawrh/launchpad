import { BrowserRouter, Route, Routes } from 'react-router-dom';
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

export default function App() {
  return (
    <BrowserRouter>
      <BrandingProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Overview />} />
            <Route path="/decisions" element={<Decisions />} />
            <Route path="/fleet" element={<Fleet />} />
            <Route path="/workloads" element={<Workloads />} />
            <Route path="/feedback" element={<Feedback />} />
            <Route path="/timing" element={<Timing />} />
            <Route path="/catalog" element={<Catalog />} />
            <Route path="/demos" element={<Demos />} />
            <Route path="/sandbox" element={<Sandbox />} />
            <Route path="/sessions/:sessionId" element={<SessionDetail />} />
          </Route>
        </Routes>
      </BrandingProvider>
    </BrowserRouter>
  );
}
