import { createContext, useContext } from 'react';
import type { BrandingProfile } from '../api/types';

export interface BrandingState {
  profile: BrandingProfile | null;
  loading: boolean;
}

export const BrandingContext = createContext<BrandingState>({
  profile: null,
  loading: false,
});

export function useBranding() {
  return useContext(BrandingContext);
}
