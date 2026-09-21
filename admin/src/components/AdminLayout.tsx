import { Link, Outlet, useLocation } from 'react-router-dom';
import { RedHatLogo, IntelLogo } from './Logo';

const NAV_ITEMS = [
  { path: '/', label: 'Dashboard' },
  { path: '/sessions', label: 'Sessions' },
  { path: '/tenants', label: 'Tenants' },
  { path: '/system', label: 'System' },
  { path: '/catalog', label: 'Catalog' },
  { path: '/intakes', label: 'Intake' },
  { path: '/events', label: 'Events' },
  { path: '/reports', label: 'Reports' },
  { path: '/analytics', label: 'Analytics' },
  { path: '/observability', label: 'Observability' },
  { path: '/roadmap/', label: 'Roadmap', document: true },
];

export default function AdminLayout() {
  const location = useLocation();

  return (
    <div className="admin-shell min-h-screen bg-[#151515] flex flex-col">
      <header className="border-b border-[#333] bg-[#151515] text-white">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <Link to="/" className="flex items-center gap-3">
                <RedHatLogo height={24} />
                <span className="text-white text-lg font-bold">X</span>
                <IntelLogo height={18} />
              </Link>
              <span className="text-[#333] mx-2">|</span>
              <span className="text-white text-sm font-semibold" style={{ fontFamily: 'Red Hat Display' }}>Launchpad Operations</span>
              <span className="text-[11px] font-medium bg-white/15 px-2 py-1 rounded">ADMIN</span>
            </div>
            <nav className="flex max-w-[65vw] gap-1 overflow-x-auto">
              {NAV_ITEMS.map((item) => {
                const isActive = item.path === '/'
                  ? location.pathname === '/'
                  : location.pathname.startsWith(item.path);
                const classes = `px-3 py-2 rounded text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-white/15 text-white'
                    : 'text-[#6A6E73] hover:text-white hover:bg-white/10'
                }`;
                return item.document ? (
                  <a
                    key={item.path}
                    href={item.path}
                    className={classes}
                  >
                    {item.label}
                  </a>
                ) : (
                  <Link
                  key={item.path}
                  to={item.path}
                    className={classes}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
        </div>
      </header>

      <div className="h-0.5 flex"><div className="flex-1 bg-[#EE0000]" /><div className="flex-1 bg-[#0071C5]" /><div className="flex-1 bg-[#3E8635]" /></div>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-[#333] bg-[#151515] text-[#6A6E73] text-sm py-6">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 flex items-center justify-between">
          <div className="flex items-center gap-3 opacity-60">
            <RedHatLogo height={18} />
            <span className="text-white text-sm font-bold mx-1">X</span>
            <IntelLogo height={14} />
          </div>
          <span>Internal operations and administration</span>
        </div>
      </footer>
    </div>
  );
}
