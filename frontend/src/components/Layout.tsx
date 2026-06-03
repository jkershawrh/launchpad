import { useEffect, useState } from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';

const NAV_ITEMS = [
  { path: '/', label: 'Platform' },
  { path: '/catalog', label: 'Catalog' },
  { path: '/demos', label: 'Demos' },
  { path: '/sandbox', label: 'Sandbox' },
];

export default function Layout() {
  const location = useLocation();
  const [healthy, setHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    fetch('/api/intelligence/fleet-health')
      .then(r => r.ok ? setHealthy(true) : setHealthy(false))
      .catch(() => setHealthy(false));
  }, []);

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--brand-dark)' }}>
      <header className="border-b border-[#333]" style={{ background: 'var(--brand-dark)' }}>
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <Link to="/" className="flex items-center gap-3">
                <img src="/logos/redhat.png" alt="Red Hat" style={{ height: '24px', width: 'auto' }} />
                <span className="text-white text-lg font-bold">X</span>
                <img src="/logos/intel.png" alt="Intel" style={{ height: '18px', width: 'auto' }} />
              </Link>
              <span className="text-[#333] mx-2">|</span>
              <span className="text-white text-sm font-semibold" style={{ fontFamily: 'Red Hat Display' }}>
                Launchpad
              </span>
            </div>

            <nav className="flex items-center gap-1">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`px-3 py-2 rounded text-sm font-medium transition ${
                    location.pathname === item.path
                      ? 'bg-white/15 text-white'
                      : 'text-[#6A6E73] hover:text-white hover:bg-white/10'
                  }`}
                >
                  {item.label}
                </Link>
              ))}
            </nav>

            <div className="flex items-center gap-3">
              {healthy !== null && (
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  healthy ? 'bg-[#3E8635]/20 text-[#3E8635]' : 'bg-[#C9190B]/20 text-[#C9190B]'
                }`}>
                  {healthy ? 'Platform Healthy' : 'Connecting...'}
                </span>
              )}
            </div>
          </div>
        </div>
      </header>

      <div className="h-0.5 flex">
        <div className="flex-1" style={{ background: 'var(--brand-primary)' }} />
        <div className="flex-1" style={{ background: 'var(--brand-secondary)' }} />
        <div className="flex-1" style={{ background: 'var(--brand-green)' }} />
      </div>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-[#333] py-6">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 flex items-center justify-between">
          <div className="flex items-center gap-3 opacity-60">
            <img src="/logos/redhat.png" alt="" style={{ height: '16px' }} />
            <span className="text-white text-sm font-bold">X</span>
            <img src="/logos/intel.png" alt="" style={{ height: '12px' }} />
          </div>
          <span className="text-[#6A6E73] text-xs">Partner AI Launchpad</span>
        </div>
      </footer>
    </div>
  );
}
