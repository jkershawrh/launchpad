import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

interface TenantInfo {
  tenant_id: string;
  tenant_slug: string;
  tier: 'pilot' | 'partner' | 'internal';
  scopes: string[];
  user_email?: string;
}

interface TenantContextValue {
  tenant: TenantInfo | null;
  isAdmin: boolean;
  isLoading: boolean;
}

const TenantCtx = createContext<TenantContextValue>({
  tenant: null,
  isAdmin: false,
  isLoading: true,
});

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = atob(parts[1].replace(/-/g, '+').replace(/_/g, '/'));
    return JSON.parse(payload);
  } catch {
    return null;
  }
}

export function TenantProvider({ children }: { children: ReactNode }) {
  const [tenant, setTenant] = useState<TenantInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = import.meta.env.VITE_AUTH_TOKEN || '';
    if (token && token.includes('.')) {
      const claims = decodeJwtPayload(token);
      if (claims) {
        setTenant({
          tenant_id: (claims.tenant_id as string) || 'internal',
          tenant_slug: (claims.tenant_slug as string) || 'internal',
          tier: (claims.tier as TenantInfo['tier']) || 'internal',
          scopes: (claims.scopes as string[]) || ['read', 'write', 'admin'],
          user_email: claims.email as string | undefined,
        });
      }
    } else {
      setTenant({
        tenant_id: 'internal',
        tenant_slug: 'internal',
        tier: 'internal',
        scopes: ['read', 'write', 'admin'],
      });
    }
    setIsLoading(false);
  }, []);

  const isAdmin = tenant?.scopes.includes('admin') || tenant?.tier === 'internal' || false;

  return (
    <TenantCtx.Provider value={{ tenant, isAdmin, isLoading }}>
      {children}
    </TenantCtx.Provider>
  );
}

export function useTenant() {
  return useContext(TenantCtx);
}
