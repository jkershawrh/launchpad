# Tenancy

## Namespace-Per-Lab Isolation

Every lab session gets its own Kubernetes namespace. The namespace name encodes the tenant and catalog item:

```
lab-{tenant_id}-{catalog_item_id}-{short_uuid}
demo-{tenant_id}-{demo_source}-{short_uuid}
sandbox-{tenant_id}-{short_uuid}
```

Each namespace includes planned security artifacts:
- ResourceQuota
- LimitRange
- RoleBinding (lab-user)
- ServiceAccount
- NetworkPolicy (restricted)
- Egress policy (deny-all-except-model-endpoint)

## Tenant Gateway Pattern

Within a tenant, all demos share a single inference gateway namespace. This avoids duplicating model-serving infrastructure per demo. When the last active demo for a tenant is reclaimed, the shared gateway namespace is cleaned up automatically.

## Tenant Types

| Type | Purpose | Example |
|------|---------|---------|
| `redhat_internal` | Red Hat teams running internal demos | Red Hat AI team |
| `intel_internal` | Intel teams running joint demos | Intel Gaudi team |
| `partner` | OEM/ISV partner evaluations | Partner OEM A |
| `client` | Customer-facing demos and PoCs | Client Demo A |
| `demo` | Conference/event demos (Summit, etc.) | Summit 2026 booth |

Each tenant carries a branding profile, default quota profile, default TTL, and optional cost center.

## Session Limits

| Limit | Default | Configurable via |
|-------|---------|-----------------|
| Active sessions per user | 2 | `MAX_ACTIVE_SESSIONS_PER_USER` env var |
| Active sessions per tenant | 5 | `MAX_ACTIVE_SESSIONS_PER_TENANT` env var |

A session counts as active if its status is one of: requested, provisioning, validating, ready, active. Users must reclaim existing sessions before requesting new ones.

## Resource Quotas Per Profile

| Profile | CPU | Memory | Storage | Max Pods | Max Routes | Gaudi | TTL Max |
|---------|-----|--------|---------|----------|------------|-------|---------|
| small | 2 | 4Gi | 20Gi | 10 | 3 | -- | 4h |
| standard | 8 | 16Gi | 50Gi | 30 | 10 | -- | 12h |
| large | 32 | 64Gi | 200Gi | 100 | 25 | 2 | 24h |

## Future: Stronger Isolation

Namespace isolation is the starting point. Future iterations will add:
- OCP Virtualization for full VM-level isolation when workloads require it
- Per-tenant network policies with fine-grained egress control
- Dedicated model-serving instances for high-security tenants
- Hardware-level isolation via dedicated Gaudi node pools per tenant
