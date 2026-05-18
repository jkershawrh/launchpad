import { useState, useEffect } from 'react';
import { Button, Card, CardBody, Content, Label, PageSection, Spinner } from '@patternfly/react-core';
import { api } from '../api/client';

interface TenantCapacity {
  slug: string;
  display_name: string;
  tier: string;
  active: boolean;
  expires_at: string | null;
  resource_quota: Record<string, number>;
  active_runs: number;
}

const TIER_COLORS: Record<string, 'blue' | 'orange' | 'green' | 'grey'> = { internal: 'blue', partner: 'orange', pilot: 'green' };

export default function CapacityDashboard() {
  const [tenants, setTenants] = useState<TenantCapacity[]>([]);
  const [totalActive, setTotalActive] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);

  const loadCapacity = async () => {
    setLoading(true);
    try {
      const resp = await api.capacityOverview() as { tenants: TenantCapacity[]; total_active_runs: number };
      setTenants(resp.tenants || []);
      setTotalActive(resp.total_active_runs || 0);
      setLoaded(true);
    } catch { setLoaded(true); }
    setLoading(false);
  };

  useEffect(() => { loadCapacity(); }, []);

  const maxCpu = Math.max(...tenants.map(t => t.resource_quota?.cpu_cores || 0), 1);
  const maxMem = Math.max(...tenants.map(t => t.resource_quota?.memory_gb || 0), 1);

  return (
    <>
      <PageSection>
        <Content>
          <Content component="h1">Capacity & Allocation</Content>
          <Content component="p" style={{ maxWidth: '780px', fontSize: '1.05rem' }}>
            Per-tenant resource allocation, quota usage, and active demo runs across the platform.
            Each partner gets isolated capacity with defined CPU, memory, and GPU limits.
          </Content>
        </Content>
      </PageSection>

      <PageSection variant="secondary">
        {!loaded && <div style={{ textAlign: 'center', padding: '32px' }}><Spinner size="lg" /> Loading capacity data...</div>}

        {loaded && (
          <>
            {/* Summary cards */}
            <div style={{ display: 'flex', gap: '16px', marginBottom: '16px' }}>
              <Card style={{ flex: 1 }}>
                <CardBody style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '2rem', fontWeight: 700, fontFamily: 'var(--pf-t--global--font--family--mono)' }}>{tenants.length}</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--rh-color--text-secondary)' }}>Total Tenants</div>
                </CardBody>
              </Card>
              <Card style={{ flex: 1 }}>
                <CardBody style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '2rem', fontWeight: 700, fontFamily: 'var(--pf-t--global--font--family--mono)', color: 'var(--rh-color--success, #3e8635)' }}>{tenants.filter(t => t.active).length}</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--rh-color--text-secondary)' }}>Active</div>
                </CardBody>
              </Card>
              <Card style={{ flex: 1 }}>
                <CardBody style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '2rem', fontWeight: 700, fontFamily: 'var(--pf-t--global--font--family--mono)', color: '#0068b5' }}>{totalActive}</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--rh-color--text-secondary)' }}>Active Runs</div>
                </CardBody>
              </Card>
              <Card style={{ flex: 1 }}>
                <CardBody style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '2rem', fontWeight: 700, fontFamily: 'var(--pf-t--global--font--family--mono)' }}>{tenants.reduce((s, t) => s + (t.resource_quota?.cpu_cores || 0), 0)}</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--rh-color--text-secondary)' }}>Total CPU Allocated</div>
                </CardBody>
              </Card>
            </div>

            {/* Tenant cards with utilization bars */}
            {tenants.map(t => {
              const cpu = t.resource_quota?.cpu_cores || 0;
              const mem = t.resource_quota?.memory_gb || 0;
              const gpu = t.resource_quota?.gpu_count || 0;
              return (
                <Card key={t.slug} style={{ marginBottom: '10px', borderLeft: `3px solid ${t.active ? (TIER_COLORS[t.tier] === 'blue' ? '#0068b5' : TIER_COLORS[t.tier] === 'orange' ? '#e67e22' : '#3e8635') : '#888'}` }}>
                  <CardBody>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>{t.display_name}</span>
                        <Label isCompact color={TIER_COLORS[t.tier] || 'grey'}>{t.tier}</Label>
                        {!t.active && <Label isCompact color="grey">Inactive</Label>}
                      </div>
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        {t.active_runs > 0 && <Label isCompact color="blue">{t.active_runs} running</Label>}
                        {t.expires_at && (
                          <span style={{ fontSize: '0.72rem', color: new Date(t.expires_at) < new Date() ? '#c9190b' : 'var(--rh-color--text-secondary)' }}>
                            {new Date(t.expires_at) < new Date() ? 'EXPIRED' : `Expires: ${new Date(t.expires_at).toLocaleDateString()}`}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Resource utilization bars */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', marginBottom: '3px' }}>
                          <span>CPU</span>
                          <span style={{ fontFamily: 'var(--pf-t--global--font--family--mono)', fontWeight: 700 }}>{cpu} cores</span>
                        </div>
                        <div style={{ height: '8px', borderRadius: '4px', background: 'var(--pf-t--global--background--color--secondary--default)', overflow: 'hidden' }}>
                          <div style={{ height: '100%', width: `${(cpu / maxCpu) * 100}%`, background: '#0068b5', borderRadius: '4px', transition: 'width 0.3s' }} />
                        </div>
                      </div>
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', marginBottom: '3px' }}>
                          <span>Memory</span>
                          <span style={{ fontFamily: 'var(--pf-t--global--font--family--mono)', fontWeight: 700 }}>{mem} GB</span>
                        </div>
                        <div style={{ height: '8px', borderRadius: '4px', background: 'var(--pf-t--global--background--color--secondary--default)', overflow: 'hidden' }}>
                          <div style={{ height: '100%', width: `${(mem / maxMem) * 100}%`, background: '#3e8635', borderRadius: '4px', transition: 'width 0.3s' }} />
                        </div>
                      </div>
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', marginBottom: '3px' }}>
                          <span>GPU</span>
                          <span style={{ fontFamily: 'var(--pf-t--global--font--family--mono)', fontWeight: 700 }}>{gpu}</span>
                        </div>
                        <div style={{ height: '8px', borderRadius: '4px', background: 'var(--pf-t--global--background--color--secondary--default)', overflow: 'hidden' }}>
                          <div style={{ height: '100%', width: gpu > 0 ? '100%' : '0%', background: '#e67e22', borderRadius: '4px', transition: 'width 0.3s' }} />
                        </div>
                      </div>
                    </div>
                  </CardBody>
                </Card>
              );
            })}
            {tenants.length === 0 && (
              <Card><CardBody style={{ color: 'var(--rh-color--text-secondary)', textAlign: 'center', padding: '24px' }}>No tenants configured. Create tenants in Admin → Tenant Management to see capacity allocation.</CardBody></Card>
            )}

            <div style={{ marginTop: '12px', textAlign: 'right' }}>
              <Button variant="link" onClick={loadCapacity} isLoading={loading}>Refresh</Button>
            </div>
          </>
        )}
      </PageSection>
    </>
  );
}
