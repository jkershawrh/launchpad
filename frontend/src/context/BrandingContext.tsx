import { useEffect, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { BrandingProfile } from '../api/types';
import { BrandingContext, type BrandingState } from './useBranding';

const DEFAULT_PROFILE: BrandingProfile = {
  branding_profile_id: 'redhat-intel-default',
  display_name: 'Red Hat + Intel Default',
  title: 'Partner AI Launchpad',
  primary_color: '#EE0000',
  secondary_color: '#0071C5',
  footer_text: 'Powered by Red Hat OpenShift and Intel',
  theme: 'default',
};

export function BrandingProvider({ children }: { children: ReactNode }) {
  const [searchParams] = useSearchParams();
  const brandId = searchParams.get('brand');
  const [state, setState] = useState<BrandingState>({
    profile: DEFAULT_PROFILE,
    loading: Boolean(brandId),
  });

  useEffect(() => {
    if (!brandId) return;
    let active = true;
    api.getBrandingProfile(brandId)
      .then((profile) => { if (active) setState({ profile, loading: false }); })
      .catch(() => { if (active) setState({ profile: DEFAULT_PROFILE, loading: false }); });
    return () => { active = false; };
  }, [brandId]);

  const value = brandId ? state : { profile: DEFAULT_PROFILE, loading: false };

  useEffect(() => {
    if (!value.profile) return;
    const root = document.documentElement;
    root.style.setProperty('--brand-primary', value.profile.primary_color);
    root.style.setProperty('--brand-secondary', value.profile.secondary_color);
  }, [value.profile]);

  return (
    <BrandingContext.Provider value={value}>
      {children}
    </BrandingContext.Provider>
  );
}
