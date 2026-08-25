import { describe, expect, it } from 'vitest';
import { getAppSurface, getNavigation } from './appSurface';

describe('application surface contract', () => {
  it('selects the external portal for the public portal hostname', () => {
    expect(getAppSurface('launchpad.apps.example.com')).toBe('portal');
  });

  it('selects operations for the admin hostname', () => {
    expect(getAppSurface('launchpad-admin.apps.example.com')).toBe('operations');
  });

  it('keeps internal navigation out of the external portal', () => {
    const paths = getNavigation('portal').map((item) => item.path);
    expect(paths).toEqual(['/', '/catalog', '/request', '/workshops/new', '/workshops', '/sessions']);
    expect(paths).not.toContain('/fleet');
    expect(paths).not.toContain('/admin');
  });

  it('exposes operations and admin navigation internally', () => {
    const paths = getNavigation('operations').map((item) => item.path);
    expect(paths).toContain('/fleet');
    expect(paths).toContain('/admin');
    expect(paths).not.toContain('/request');
  });
});
