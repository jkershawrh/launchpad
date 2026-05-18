import { Link, Outlet, useLocation } from 'react-router-dom';
import { useBranding } from '../context/BrandingContext';

const NAV_ITEMS = [
  { path: '/', label: 'Home' },
  { path: '/demos', label: 'Demos' },
  { path: '/sandbox', label: 'Sandbox' },
];

export default function Layout() {
  const location = useLocation();
  const { profile } = useBranding();

  const primaryColor = profile?.primary_color || '#EE0000';
  const headerBg = profile?.metadata?.header_bg as string || '#151515';
  const footerText = profile?.footer_text || 'Powered by Red Hat OpenShift and Intel';
  const logoRefs = profile?.logo_refs || ['/logos/redhat.png', '/logos/intel.png'];

  const brandParam = new URLSearchParams(location.search).get('brand');
  const brandQuery = brandParam ? `?brand=${brandParam}` : '';

  return (
    <div className="min-h-screen bg-[#F0F0F0] flex flex-col">
      <header style={{ backgroundColor: headerBg }} className="text-white">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <Link to={`/${brandQuery}`} className="flex items-center gap-4">
              {logoRefs.map((logo, i) => (
                <span key={i} className="flex items-center gap-4">
                  {i > 0 && <span className="text-white text-xl font-bold mx-2">X</span>}
                  <img
                    src={logo}
                    alt=""
                    style={{ height: i === 0 ? '28px' : '22px', width: 'auto' }}
                  />
                </span>
              ))}
            </Link>
            <nav className="flex gap-1">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.path}
                  to={`${item.path}${brandQuery}`}
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

      <div style={{ backgroundColor: primaryColor }} className="h-0.5" />

      <main className="flex-1">
        <Outlet />
      </main>

      <footer style={{ backgroundColor: headerBg }} className="text-gray-400 text-sm py-6">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {logoRefs.map((logo, i) => (
              <span key={i} className="flex items-center gap-3">
                {i > 0 && <span className="text-white text-sm font-bold mx-1">X</span>}
                <img src={logo} alt="" style={{ height: '16px', width: 'auto', opacity: 0.7 }} />
              </span>
            ))}
          </div>
          <span>{footerText}</span>
        </div>
      </footer>
    </div>
  );
}
