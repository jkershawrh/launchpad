import { Link, Outlet, useLocation } from 'react-router-dom';
import { RedHatLogo, IntelLogo } from './Logo';

const NAV_ITEMS = [
  { path: '/', label: 'Dashboard' },
  { path: '/sessions', label: 'Sessions' },
  { path: '/tenants', label: 'Tenants' },
  { path: '/system', label: 'System' },
  { path: '/catalog', label: 'Catalog' },
  { path: '/reports', label: 'Reports' },
  { path: '/analytics', label: 'Analytics' },
];

export default function AdminLayout() {
  const location = useLocation();

  return (
    <div className="min-h-screen bg-[#F0F0F0] flex flex-col">
      <header className="bg-[#151515] text-white">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <Link to="/" className="flex items-center gap-5">
              <RedHatLogo height={28} />
              <span className="text-white text-xl font-bold mx-2">X</span>
              <IntelLogo height={22} />
              <span className="text-xs font-medium bg-white/15 px-2 py-0.5 rounded ml-2">ADMIN</span>
            </Link>
            <nav className="flex gap-1">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`px-3 py-2 rounded text-sm font-medium transition-colors ${
                    location.pathname === item.path
                      ? 'bg-white/15 text-white'
                      : 'text-gray-300 hover:text-white hover:bg-white/10'
                  }`}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        </div>
      </header>

      <div className="bg-[#EE0000] h-0.5" />

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="bg-[#151515] text-gray-400 text-sm py-6">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <RedHatLogo height={18} />
            <span className="text-white text-sm font-bold mx-1">X</span>
            <IntelLogo height={14} />
          </div>
          <span>Partner AI Launchpad — Administration</span>
        </div>
      </footer>
    </div>
  );
}
