import { NavLink, Outlet } from 'react-router-dom';
import { useConfig, isPageEnabled } from '../context/LaunchpadConfig';
import {
  Brand,
  Masthead,
  MastheadBrand,
  MastheadContent,
  MastheadMain,
  MastheadToggle,
  Nav,
  NavItem,
  NavList,
  Page,
  PageSidebar,
  PageSidebarBody,
  PageToggleButton,
  SkipToContent,
  Toolbar,
  ToolbarContent,
  ToolbarItem,
  Label,
  Divider,
} from '@patternfly/react-core';
import { BarsIcon } from '@patternfly/react-icons';
import { useHealth } from '../api/hooks';
import { useTenant } from '../context/TenantContext';

const navSections = [
  {
    title: 'Understand',
    items: [
      { path: '/', label: 'Overview' },
      { path: '/architecture', label: 'Architecture' },
    ],
  },
  {
    title: 'Experience',
    items: [
      { path: '/overdrive', label: 'Routing Engine' },
      { path: '/tokenizer', label: 'Tokenizer & Cost' },
      { path: '/try-it', label: 'Try It' },
      { path: '/workload', label: 'Workload Simulation' },
      { path: '/agent', label: 'Research Agent' },
      { path: '/swarm', label: 'Agent Swarm' },
      { path: '/training', label: 'Train + Serve' },
      { path: '/optimization', label: 'Optimization' },
      { path: '/replay', label: 'Replay Comparison' },
      { path: '/recovery', label: 'Recovery & Resilience' },
    ],
  },
  {
    title: 'Observe',
    items: [
      { path: '/cockpit', label: 'Cockpit' },
      { path: '/fleet-intel', label: 'Fleet Intelligence' },
      { path: '/capacity', label: 'Capacity & Allocation' },
      { path: '/operations', label: 'Operations' },
      { path: '/governance', label: 'Governance Audit' },
      { path: '/docs', label: 'Documentation' },
    ],
  },
  {
    title: 'Discover',
    items: [
      { path: '/gallery', label: 'Publishing House' },
    ],
  },
  {
    title: 'Admin',
    items: [
      { path: '/admin/tenants', label: 'Tenant Management' },
    ],
  },
];

export default function AppLayout() {
  const { data: health } = useHealth();
  const { tenant, isAdmin } = useTenant();

  const config = useConfig();
  const pageEnabled = (path: string) => {
    const page = path === '/' ? 'overview' : path.replace('/', '').replace('/tenants', '');
    return isPageEnabled(config, page);
  };

  const visibleSections = navSections
    .filter(s => {
      if (s.title === 'Admin' && !isAdmin) return false;
      return true;
    })
    .map(s => ({
      ...s,
      items: s.items.filter(item => pageEnabled(item.path)),
    }))
    .filter(s => s.items.length > 0);

  const masthead = (
    <Masthead>
      <MastheadMain>
        <MastheadToggle>
          <PageToggleButton variant="plain" aria-label="Menu">
            <BarsIcon />
          </PageToggleButton>
        </MastheadToggle>
        <MastheadBrand>
          <Brand
            src="/intel-logo.svg"
            alt="Intel"
            heights={{ default: '28px' }}
          />
          <Divider orientation={{ default: 'vertical' }} style={{ margin: '0 10px' }} />
          <Brand
            src="/redhat-logo.svg"
            alt="Red Hat"
            heights={{ default: '28px' }}
          />
          <Divider orientation={{ default: 'vertical' }} style={{ margin: '0 10px' }} />
          <span style={{ fontSize: '0.95rem', fontWeight: 600, whiteSpace: 'nowrap' }}>
            Intel-Red Hat AI Inference Platform
          </span>
        </MastheadBrand>
      </MastheadMain>
      <MastheadContent>
        <Toolbar isStatic>
          <ToolbarContent>
            <ToolbarItem>
              {tenant && (
                <Label isCompact color={tenant.tier === 'internal' ? 'blue' : 'orange'}>
                  {tenant.tenant_slug}
                </Label>
              )}
            </ToolbarItem>
            <ToolbarItem align={{ default: 'alignEnd' }}>
              <Label
                color={health?.status === 'healthy' ? 'green' : 'red'}
              >
                {health?.status === 'healthy' ? 'Platform Healthy' : 'Connecting...'}
              </Label>
            </ToolbarItem>
          </ToolbarContent>
        </Toolbar>
      </MastheadContent>
    </Masthead>
  );

  const sidebar = (
    <PageSidebar>
      <PageSidebarBody>
        <Nav aria-label="Main navigation">
          {visibleSections.map((section) => (
            <div key={section.title}>
              <div style={{
                padding: '12px 16px 4px', fontSize: '0.7rem', fontWeight: 700,
                textTransform: 'uppercase', letterSpacing: '0.05em',
                color: 'var(--pf-t--global--text--color--subtle)',
              }}>
                {section.title}
              </div>
              <NavList>
                {section.items.map(({ path, label }) => (
                  <NavItem key={path}>
                    <NavLink to={path} className={({ isActive }) => isActive ? 'pf-m-current' : ''}>
                      {label}
                    </NavLink>
                  </NavItem>
                ))}
              </NavList>
            </div>
          ))}
        </Nav>
      </PageSidebarBody>
    </PageSidebar>
  );

  return (
    <Page
      masthead={masthead}
      sidebar={sidebar}
      skipToContent={<SkipToContent href="#main-content">Skip to content</SkipToContent>}
    >
      <div id="main-content">
        <Outlet />
      </div>
    </Page>
  );
}
