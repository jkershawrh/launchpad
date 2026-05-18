import { BrowserRouter, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import { BrandingProvider } from './context/BrandingContext';
import Catalog from './pages/Catalog';
import Demos from './pages/Demos';
import Home from './pages/Home';
import Sandbox from './pages/Sandbox';
import SessionDetail from './pages/SessionDetail';

export default function App() {
  return (
    <BrowserRouter>
      <BrandingProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Home />} />
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
