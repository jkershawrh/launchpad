import { useState, useEffect } from 'react';
import { Button, Card, CardBody, Content, Label, PageSection, TextInput } from '@patternfly/react-core';
import { api } from '../api/client';
import { useTenant } from '../context/TenantContext';

interface TenantRow {
  slug: string;
  display_name: string;
  tier: string;
  active: boolean;
}

export default function TenantAdmin() {
  const { isAdmin } = useTenant();
  const [tenants, setTenants] = useState<TenantRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [slug, setSlug] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState('');

  const loadTenants = async () => {
    try {
      const resp = await api.listTenants() as { tenants: TenantRow[] };
      setTenants(resp.tenants || []);
      setLoaded(true);
    } catch { setMessage('Failed to load tenants (DB may not be connected)'); setLoaded(true); }
  };

  useEffect(() => { if (isAdmin) loadTenants(); }, [isAdmin]);

  const createTenant = async () => {
    if (!slug || !displayName) return;
    setCreating(true); setMessage('');
    try {
      const resp = await api.createTenant(slug, displayName) as Record<string, unknown>;
      setMessage(`Tenant "${slug}" created. ${resp.note || ''}`);
      setSlug(''); setDisplayName('');
      await loadTenants();
    } catch (e) { setMessage(`Failed: ${e}`); }
    setCreating(false);
  };

  if (!isAdmin) {
    return (
      <PageSection>
        <Content><Content component="h1">Tenant Administration</Content></Content>
        <Card><CardBody>Admin access required.</CardBody></Card>
      </PageSection>
    );
  }

  return (
    <>
      <PageSection>
        <Content>
          <Content component="h1">Tenant Administration</Content>
          <Content component="p">Manage partner tenants, API keys, and resource allocations.</Content>
        </Content>
      </PageSection>

      <PageSection variant="secondary">
        <Card style={{ maxWidth: '600px', marginBottom: '16px' }}>
          <CardBody>
            <div style={{ fontWeight: 700, marginBottom: '12px' }}>Create Tenant</div>
            <div style={{ display: 'flex', gap: '8px', marginBottom: '8px', flexWrap: 'wrap' }}>
              <TextInput value={slug} onChange={(_e, v) => setSlug(v)} placeholder="Slug (e.g. acme-corp)" style={{ maxWidth: '200px' }} />
              <TextInput value={displayName} onChange={(_e, v) => setDisplayName(v)} placeholder="Display Name" style={{ maxWidth: '250px' }} />
              <Button variant="primary" onClick={createTenant} isLoading={creating} isDisabled={!slug || !displayName}>Create</Button>
            </div>
            {message && <div style={{ fontSize: '0.82rem', color: 'var(--pf-t--global--text--color--subtle)', marginTop: '4px' }}>{message}</div>}
          </CardBody>
        </Card>

        <Card>
          <CardBody>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontWeight: 700 }}>Tenants ({tenants.length})</span>
              <Button variant="link" onClick={loadTenants} isDisabled={!loaded}>Refresh</Button>
            </div>
            {!loaded && <div style={{ color: 'var(--pf-t--global--text--color--subtle)', fontSize: '0.85rem' }}>Loading tenants...</div>}
              {loaded && tenants.length === 0 && <div style={{ color: 'var(--pf-t--global--text--color--subtle)', fontSize: '0.85rem' }}>No tenants found (DB may not be connected)</div>}
              {tenants.map(t => (
                <div key={t.slug} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 0', borderBottom: '1px solid var(--pf-t--global--border--color--default)' }}>
                  <span style={{ fontWeight: 600, minWidth: '120px' }}>{t.slug}</span>
                  <span style={{ flex: 1, color: 'var(--pf-t--global--text--color--subtle)' }}>{t.display_name}</span>
                  <Label isCompact color={t.tier === 'internal' ? 'blue' : t.tier === 'partner' ? 'orange' : 'green'}>{t.tier}</Label>
                  <Label isCompact color={t.active ? 'green' : 'grey'}>{t.active ? 'Active' : 'Inactive'}</Label>
                </div>
              ))}
          </CardBody>
        </Card>
      </PageSection>
    </>
  );
}
