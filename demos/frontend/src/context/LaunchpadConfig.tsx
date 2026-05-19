import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

interface LaunchpadConfig {
  pages: string[];
  gateway_url: string;
  demo_name: string;
  branding: string;
}

const DEFAULT_CONFIG: LaunchpadConfig = {
  pages: ['all'],
  gateway_url: '',
  demo_name: 'Intel x Red Hat AI Platform',
  branding: 'default',
};

const ConfigContext = createContext<LaunchpadConfig>(DEFAULT_CONFIG);

export function LaunchpadConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<LaunchpadConfig>(DEFAULT_CONFIG);

  useEffect(() => {
    fetch('/config.json')
      .then((res) => res.json())
      .then((data) => setConfig({ ...DEFAULT_CONFIG, ...data }))
      .catch(() => setConfig(DEFAULT_CONFIG));
  }, []);

  return (
    <ConfigContext.Provider value={config}>
      {children}
    </ConfigContext.Provider>
  );
}

export function useConfig() {
  return useContext(ConfigContext);
}

export function isPageEnabled(config: LaunchpadConfig, page: string): boolean {
  return config.pages.includes('all') || config.pages.includes(page);
}
