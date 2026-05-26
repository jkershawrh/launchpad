# Launchpad — Status & Next Steps

## What We Built

Launchpad is a self-service AI demo platform for the Intel x Red Hat partnership. Partners and customers order demos through RHDP, get isolated environments with real inference on Intel Gaudi 3 and Xeon 6 hardware via MaaS, and everything cleans up automatically.

- **25 catalog items** — 10 custom Intel demos, 7 official Summit AI quickstarts, 4 sandboxes, 4 originals
- **3 provisioning modes** — self-service (on-demand), workshops (40 users batch), persistent (always-on)
- **Full lifecycle** — 17-state machine: request > provision > validate > ready > activate > reclaim
- **4 adapter tiers** — mock (testing), local (podman), openshift (K8s API), rhdp (Sandbox API)
- **Security** — SSO, API keys, session limits, PSS, NetworkPolicy, credential scrubbing, kubeconfig (not --token)
- **RHDP integration** — Sandbox API client, AgnosticV configs, ArgoCD Helm chart, Showroom content
- **AAP client** — ready to wire into job templates (AAP 4.5 on infra01)
- **AI brand generation** — LLM-powered branding from company name
- **422 unit tests** — all TDD red/green
- **28 local E2E tests** — real containers, real inference
- **GitHub Actions CI** — tests, lint, TypeScript, Helm validation, image builds on every push

---

## What's Done

| Component | Status |
|-----------|--------|
| Backend API on infra01 | Running (4 pods) |
| Partner portal | Running |
| Admin dashboard | Running |
| Sandbox API connection | Verified (12 CNV clusters) |
| Container images | Built locally, tagged for quay.io/rhpds |
| AgnosticV configs | Branch `launchpad-demos` pushed, **ready for PR** (52 files, 12 catalog items) |
| Tenant Helm chart | `tenant/bootstrap/` — ArgoCD deploys per-user namespaces |
| Showroom content | `content/` — 12 AsciiDoc lab pages |
| CI | Green on latest commit |
| Security | Keys rotated, history scrubbed, push protection enabled |
| README | Cleaned for public (no internal project references) |

---

## Ready for PR — AgnosticV

Branch `launchpad-demos` in `rhpds/agnosticv` — 4 commits, 52 files:

| Config | Files | Purpose |
|--------|-------|---------|
| `launchpad-cluster/` | 7 | Shared base infra (CNV cluster, deployed once) |
| `launchpad-demo-tenant/` | 5 | Generic demo tenant (default catalog item) |
| 10 individual demo tenants | 4 each | One per Intel demo (agent-swarm, aiops-copilot, etc.) |

Follows the `ai-qs-*` pattern exactly. Each tenant config references `rhpds/launchpad` for the Helm chart and Showroom content.

**Create PR:** https://github.com/rhpds/agnosticv/compare/master...launchpad-demos

---

## Blocked — Needs Tony

### 1. Sandbox API `app` role token
**What:** `sandbox-cli jwt issue --name launchpad --role app`
**Why:** Current token (`shared-cluster-manager`) can manage clusters but can't create placements. Need `app` role to provision demo namespaces on CNV clusters.
**Unblocks:** Real end-to-end demo provisioning

### 2. quay.io push access
**What:** Add jkershaw to `rhpds` org with push access
**Why:** Two container images need to be pushed: `quay.io/rhpds/launchpad-demo-frontend` and `quay.io/rhpds/launchpad-gateway`. Built locally, can't push.
**Unblocks:** Demos deploying on CNV clusters

### 3. asset_uuid assignment
**What:** Real UUIDs for cluster and tenant configs (currently `TBD-assign-with-tony`)
**Unblocks:** Configs passing RHDP catalog validation

### 4. AgnosticV PR review
**What:** Review branch `launchpad-demos` in `rhpds/agnosticv` (52 files, 12 catalog items)
**Unblocks:** Demos appearing in RHDP catalog

---

## Meeting with Tony — Agenda

### Show
1. `launchpad-demos` branch in agnosticv — follows `ai-qs-rag` pattern exactly
2. `rhpds/launchpad` repo — tenant Helm chart, Showroom content, backend API
3. How the two repos connect: agnosticv configs point to launchpad for ArgoCD + Showroom

### Ask
1. **CI pipeline walkthrough** — dev > integration > prod process, how to test on a dev CNV cluster
2. **Sandbox API `app` token** — can he issue one via `sandbox-cli`?
3. **quay.io access** — who grants push access to `rhpds` org?
4. **asset_uuid** — what UUIDs for our cluster and tenant configs?
5. **Versioning** — tag releases or use `main` for dev?
6. **Showroom content** — separate repo or keep in `rhpds/launchpad`?

### Not for Tony (Ashok's domain)
- Model deployment on GPU clusters
- MaaS endpoint configuration
- Intel hardware allocation

---

## How the RHDP Pipeline Works

```
User orders demo from RHDP catalog
        |
        v
+-- Babylon (Orchestration) ----------------------------------------+
|  Reads catalog item from AgnosticV                                 |
|  Provisions cluster from Sandbox API pool                          |
|  Triggers AgnosticD deployer                                       |
+---------------+----------------------------------------------------+
                |
                v
+-- AgnosticD (Deployment Automation) -------------------------------+
|  Runs Ansible workloads defined in AgnosticV common.yaml:          |
|  1. ocp4_workload_tenant_keycloak_user (SSO user)                  |
|  2. ocp4_workload_tenant_namespace (quotas, RBAC)                  |
|  3. ocp4_workload_litellm_virtual_keys (MaaS access)               |
|  4. ocp4_workload_gitops_bootstrap (ArgoCD Application)            |
|  5. ocp4_workload_showroom (lab UI)                                |
+---------------+----------------------------------------------------+
                |
                v
+-- ArgoCD / GitOps -------------------------------------------------+
|  Deploys tenant/bootstrap/ Helm chart from rhpds/launchpad          |
|  Per-user namespace gets:                                           |
|  - Demo frontend (filtered pages)                                   |
|  - Inference gateway (LiteLLM virtual key)                          |
|  - PostgreSQL                                                       |
|  - NetworkPolicy + labels                                           |
|  - Route                                                            |
+---------------+----------------------------------------------------+
                |
                v
+-- Sandbox API (Cluster Pool) --------------------------------------+
|  Manages namespace placement on CNV clusters                        |
|  Tracks capacity, quotas, placement lifecycle                       |
|  Provides SA token + ingress domain + console URL                   |
+--------------------------------------------------------------------+
```

### What we own vs what RHDP owns

| We Own | RHDP Owns |
|--------|-----------|
| AgnosticV config files (what to deploy) | Babylon orchestration (when/where to deploy) |
| Helm chart (what goes in the namespace) | AgnosticD execution engine (how to run workloads) |
| Showroom content (lab instructions) | Showroom runtime (the UI framework) |
| Container images (frontend + gateway) | Cluster pool (Sandbox API + CNV fleet) |
| Launchpad backend API (lifecycle, catalog) | RHDP catalog UI (demo.redhat.com) |

---

## After Blockers Clear — Execution Sequence

1. Push images to quay.io
2. Test CI on dev cluster: `purpose: dev` via Sandbox API
3. AgnosticD runs workloads > ArgoCD deploys Helm chart > namespace ready
4. Verify Showroom + frontend + gateway + real inference end-to-end
5. Run cluster E2E > green receipt
6. Move from dev > integration > prod (with Tony's guidance)

---

## Technical Debt (Low Priority)

| Item | Notes |
|------|-------|
| AAP Job Templates | Client built, not wired into provisioner. Wire once job templates are created on AAP controller |
| AI brand generation on live LLM | Generator built, needs LiteMaaS endpoint configured to run for real |
| Dependabot alerts (15) | Upstream dep vulnerabilities, not our code |
| `test_demo_migration` skipped in CI | Meta-test runs full suite as subprocess, needs podman |
| Admin system monitor tests skipped in CI | Need podman on runner |
| Re-enable branch protection | Currently bypassed for direct pushes to main |

---

## Key Links

| Resource | URL |
|----------|-----|
| Launchpad repo | https://github.com/rhpds/launchpad |
| AgnosticV branch | https://github.com/rhpds/agnosticv/tree/launchpad-demos |
| AgnosticV PR | https://github.com/rhpds/agnosticv/compare/master...launchpad-demos |

---

## Manager's Guidance

> Package your demos as CIs the same way we create all other CIs. Use virtualized environments on CNV clusters. Use models through MaaS. Coordinate GPU deployment with Ashok. Work with Tony on the agnosticd/agnosticv pipeline.

We're aligned. Everything uses MaaS for inference (no GPU deployment), targets CNV clusters via Sandbox API, and follows the agnosticv CI pattern.
