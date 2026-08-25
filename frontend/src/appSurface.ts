export type AppSurface = 'portal' | 'operations';

export interface NavigationItem {
  path: string;
  label: string;
}

const PORTAL_NAVIGATION: NavigationItem[] = [
  { path: '/', label: 'Dashboard' },
  { path: '/catalog', label: 'Catalog' },
  { path: '/request', label: 'Request a Lab' },
  { path: '/sessions', label: 'My Labs' },
];

const OPERATIONS_NAVIGATION: NavigationItem[] = [
  { path: '/', label: 'Overview' },
  { path: '/decisions', label: 'Decisions' },
  { path: '/fleet', label: 'Fleet' },
  { path: '/workloads', label: 'Workloads' },
  { path: '/feedback', label: 'Feedback' },
  { path: '/timing', label: 'Timing' },
  { path: '/admin', label: 'Admin' },
];

export function getAppSurface(hostname: string, override?: string | null): AppSurface {
  if (override === 'operations' || override === 'admin') return 'operations';
  if (override === 'portal') return 'portal';
  return hostname.toLowerCase().includes('admin') ? 'operations' : 'portal';
}

export function getNavigation(surface: AppSurface): NavigationItem[] {
  return surface === 'operations' ? OPERATIONS_NAVIGATION : PORTAL_NAVIGATION;
}

