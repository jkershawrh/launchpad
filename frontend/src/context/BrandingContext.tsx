import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { BrandingProfile } from '../api/types';

interface BrandingState {
  profile: BrandingProfile | null;
  loading: boolean;
}

const DEFAULT_PROFILE: BrandingProfile = {
  branding_profile_id: 'redhat-intel-default',
  display_name: 'Red Hat + Intel Default',
  title: 'Partner AI Launchpad',
  primary_color: '#EE0000',
  secondary_color: '#0071C5',
  footer_text: 'Powered by Red Hat OpenShift and Intel',
  theme: 'default',
};

const BrandingContext = createContext<BrandingState>({
  profile: DEFAULT_PROFILE,
  loading: false,
});

export function BrandingProvider({ children }: { children: ReactNode }) {
  const [searchParams] = useSearchParams();
  const [state, setState] = useState<BrandingState>({
    profile: DEFAULT_PROFILE,
    loading: true,
  });

  useEffect(() => {
    const brandId = searchParams.get('brand');
    if (brandId) {
      api.getBrandingProfile(brandId)
        .then((profile) => setState({ profile, loading: false }))
        .catch(() => setState({ profile: DEFAULT_PROFILE, loading: false }));
    } else {
      setState({ profile: DEFAULT_PROFILE, loading: false });
    }
  }, [searchParams]);

  useEffect(() => {
    if (!state.profile) return;
    const root = document.documentElement;
    root.style.setProperty('--brand-primary', state.profile.primary_color);
    root.style.setProperty('--brand-secondary', state.profile.secondary_color);
  }, [state.profile]);

  return (
    <BrandingContext.Provider value={state}>
      {children}
    </BrandingContext.Provider>
  );
}

export function useBranding() {
  return useContext(BrandingContext);
}
