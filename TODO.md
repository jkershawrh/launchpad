# Launchpad — Status & Next Steps

## What We Built

Launchpad is a self-service AI demo platform for the Intel x Red Hat partnership. Partners and customers order demos through a branded portal, get isolated environments with real inference on Intel Gaudi 3 and Xeon 6 hardware, and everything cleans up automatically.

- **25 catalog items** — 10 custom Intel demos, 7 official Summit AI quickstarts, 4 sandboxes, 4 originals
- **3 provisioning modes** — self-service (on-demand), workshops (40 users batch), persistent (always-on)
- **Full lifecycle** — 17-state machine: request → provision → validate → ready → activate → reclaim
- **4 adapter tiers** — mock (testing), local (podman), openshift (K8s API), rhdp (Sandbox API)
- **Security** — SSO, API keys, session limits, PSS, NetworkPolicy, credential scrubbing, kubeconfig (not --token)
- **RHDP integration** — Sandbox API client, AgnosticV configs, ArgoCD Helm chart, Showroom content
- **AAP client** — ready to wire into job templates (AAP 4.5 on infra01)
- **AI brand generation** — LLM-powered branding from company name
- **422 unit tests** — all TDD red/green
- **28 local E2E tests** — real containers, real inference
- **GitHub Actions CI** — tests, lint, TypeScript, Helm validation, image builds on every push

---

## What's Working Today

| Component | Status |
|-----------|--------|
| Backend API on infra01 | Running (4 pods) |
| Partner portal | Running |
| Admin dashboard | Running |
| Sandbox API connection | Verified (12 CNV clusters) |
| Container images | Built locally, tagged for quay.io/rhpds |
| AgnosticV configs | Branch `launchpad-demos` in rhpds/agnosticv |
| CI | Green |
| Security | Keys rotated, history scrubbed, push protection enabled |

---

## Blocked — Needs Team Help

### 1. Sandbox API `app` role token
**Who:** Tony Kay or admin with `sandbox-cli` access
**What:** `sandbox-cli jwt issue --name launchpad --role app`
**Why:** Our current token (`shared-cluster-manager`) can manage clusters but can't create placements. Need `app` role to provision demo namespaces on CNV clusters.
**Unblocks:** Real end-to-end demo provisioning

### 2. quay.io push access
**Who:** rhpds org admin on quay.io
**What:** Add jkershaw to `rhpds` org with push access
**Why:** Two container images need to be pushed: `quay.io/rhpds/launchpad-demo-frontend` and `quay.io/rhpds/launchpad-gateway`. Built locally, can't push.
**Unblocks:** Demos deploying on CNV clusters

### 3. AgnosticV PR review
**Who:** Tony Kay / Nate Stephany
**What:** Review branch `launchpad-demos` in `rhpds/agnosticv`
**Why:** 12 CI configs (1 cluster + 11 tenants) following the ai-qs-* pattern. Ready for review.
**Unblocks:** Demos appearing in RHDP catalog

---

## Meeting with Tony — Agenda

### Show
1. `launchpad-demos` branch in agnosticv — follows ai-qs-rag pattern exactly
2. `rhpds/launchpad` repo — tenant Helm chart, Showroom content, backend API
3. SVG architecture diagrams in `docs/diagrams/`

### Ask
1. **CI pipeline walkthrough** — dev → integration → prod process
2. **Dev cluster testing** — how to test our CI on a dev CNV cluster
3. **Sandbox API `app` token** — can he issue one?
4. **quay.io access** — who grants push access to `rhpds` org?
5. **asset_uuid** — what UUIDs for our cluster and tenant configs?
6. **Versioning** — tag releases or use `main` for dev?
7. **Showroom content** — separate repo or keep in `rhpds/launchpad`?

### Don't ask Tony (Ashok's domain)
- Model deployment on GPU clusters
- MaaS endpoint configuration
- Intel hardware allocation

---

## After Blockers Clear — Execution Sequence

1. Push images to quay.io
2. Create real Sandbox API placement on a dev CNV cluster
3. Deploy demo end-to-end (namespace + gateway + frontend + real inference)
4. Run cluster E2E → green receipt
5. Showroom screenshots from running demo
6. Move from dev to integration to prod

---

## Technical Debt (Low Priority)

| Item | Notes |
|------|-------|
| AAP Job Templates | Client built, not wired into provisioner. Wire once job templates are created on AAP controller |
| AI brand generation on live LLM | Generator built, needs LiteMaaS endpoint configured to run for real |
| Dependabot alerts (15) | Upstream dep vulnerabilities, not our code |
| `test_demo_migration` skipped in CI | Meta-test runs full suite as subprocess, needs podman |
| Admin system monitor tests skipped in CI | Need podman on runner |

---

## Key Links

| Resource | URL |
|----------|-----|
| Launchpad repo | https://github.com/rhpds/launchpad |
| AgnosticV branch | https://github.com/rhpds/agnosticv/tree/launchpad-demos |
| Launchpad on infra01 | https://launchpad.apps.ocpv-infra01.dal12.infra.demo.redhat.com |
| Admin on infra01 | https://launchpad-admin.apps.ocpv-infra01.dal12.infra.demo.redhat.com |
| Sandbox API | (via VPN + SANDBOX_API_URL env var) |

---

## Manager's Guidance

> Package your demos as CIs the same way we create all other CIs. Use virtualized environments on CNV clusters. Use models through MaaS. Coordinate GPU deployment with Ashok. Work with Tony on the agnosticd/agnosticv pipeline.

We're aligned. Everything uses MaaS for inference (no GPU deployment), targets CNV clusters via Sandbox API, and follows the agnosticv CI pattern.
