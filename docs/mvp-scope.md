# Build Matrix

## Catalog (25 items)

| Category | Count | Items |
|----------|-------|-------|
| Official AI Quickstarts | 7 | RAG Chatbot, Data Governance, PPE Compliance, Product Recommendation, IT Self-Service, LLM CPU Serving, vLLM Tool Calling |
| Custom Demos | 10 | Inference Overdrive, Enterprise RAG, AIOps Copilot, Governed Agent, Agent Swarm, Research Agent, Recovery Demo, Workload Generator, Training Demo, Replay Comparison |
| Originals | 3 | Inference Overdrive Quick Start, Build a RAG App, Mixed AI Sandbox |
| Open Sandboxes | 5 | Full Platform Sandbox, Minimal, AI Dev, Full Stack, Custom |

## RHDP Integration

| Component | Status | Details |
|-----------|--------|---------|
| Sandbox API client | Done | JWT auth, placements CRUD, cluster config, sandbox accounts |
| RHDP pool adapter | Done | Claims/releases namespaces via Sandbox API |
| RHDP provisioning adapter | Done | Deploys workloads on claimed namespaces |
| RHDP validation/cleanup | Done | Validates placements, releases on reclaim |
| `LAUNCHPAD_MODE=rhdp` wiring | Done | Hybrid routing — per-catalog-item provisioner selection |
| Sandbox API connection | Verified | 10 CNV clusters visible, login working |
| `app` role token | Pending | Need admin to issue — required for placement creation |
| End-to-end placement test | Blocked | Waiting on app token |

## AgnosticV Configs (deploy/agnosticv/)

| Config | Type | Status |
|--------|------|--------|
| `launchpad-cluster` | Base infra (RHOAI, GitOps, Keycloak) | Done — dev + event variants |
| `launchpad-inference-overdrive-tenant` | Per-user demo | Done — 5 models |
| `launchpad-enterprise-rag-tenant` | Per-user demo | Done — 2 models |
| `launchpad-aiops-copilot-tenant` | Per-user demo | Done — 2 models |
| `launchpad-governed-agent-tenant` | Per-user demo | Done — 3 models |
| `launchpad-agent-swarm-tenant` | Per-user demo | Done — 3 models |
| `launchpad-research-agent-tenant` | Per-user demo | Done — 2 models |
| `launchpad-recovery-demo-tenant` | Per-user demo | Done — 5 models |
| `launchpad-workload-generator-tenant` | Per-user demo | Done — 5 models |
| `launchpad-training-demo-tenant` | Per-user demo | Done — 1 model |
| `launchpad-replay-comparison-tenant` | Per-user demo | Done — 3 models |
| `launchpad-demo-tenant` | Generic (all demos) | Done |
| Submit to `rhpds/agnosticv` | PR | Pending |

## Tenant Bootstrap (tenant/bootstrap/)

| Component | Status | Details |
|-----------|--------|---------|
| Helm chart | Done | ArgoCD-deployable, parameterized by demo |
| Demo frontend deployment | Done | Runtime page filtering via ConfigMap |
| Inference gateway deployment | Done | LiteLLM virtual key + routing policy |
| PostgreSQL | Done | Gateway state storage |
| Route | Done | HTTPS edge-terminated OpenShift route |
| Container images | Pending | Need to build + push to quay.io |

## Showroom Lab Content (content/)

| Page | Status |
|------|--------|
| Index — overview + architecture | Done |
| Accessing the Cluster — pods, routes, credentials | Done |
| Inference Overdrive — routing, latency, architecture | Done |
| Enterprise RAG — retrieval pipeline, with/without RAG | Done |
| Agent Swarm — multi-agent coordination | Done |
| Research Agent — query decomposition, citations | Done |
| AIOps Copilot — classification, RCA, governance | Done |
| Governed Agent — risk gates, audit trail | Done |
| Hardware Recovery — failover simulation | Done |
| Workload Generator — storm, barrage, token cannon | Done |
| Model Training — fine-tuning, evaluation | Done |
| Replay Comparison — Xeon vs Gaudi benchmarking | Done |
| Screenshots | Pending |

## Models (via LiteMaaS)

| Model | Hardware | Gaudi Cards | Status |
|-------|----------|-------------|--------|
| Granite 3.2 8B Instruct | Gaudi 3 | 4 | Running |
| Llama 3.1 70B | CPU (llama.cpp) | — | Running |
| DeepSeek R1 Distill Qwen 14B | Gaudi 3 | 4 | Running |
| Microsoft Phi-4 | Gaudi 3 | 2 | Running |
| Qwen3 14B | Gaudi 3 | 8 (2 replicas) | Running |
| **Total Gaudi cards in use** | | **14 of 24** | **10 free** |

## Infrastructure

| Cluster | Role | Status |
|---------|------|--------|
| MaaS cluster | Model serving (Gaudi 3 + Xeon 6) | Running — 5 models, RHOAI 2.25 |
| Launchpad cluster | Launchpad platform (backend, portal, admin) | Running — 4 pods |
| CNV pool | Demo deployment targets via Sandbox API | 10+ clusters |
| Launchpad base cluster | Shared infra for custom demos | Pending — needs onboarding |

## Backend Adapters

| Adapter Tier | Pool | Provisioning | Validation | Cleanup | Status |
|-------------|------|-------------|-----------|---------|--------|
| Mock | MockPool | MockProvisioning | MockValidation | — | Working — 228 tests |
| Local | MockPool | LocalProvisioning (podman) | LocalValidation | LocalCleanup | Working |
| OpenShift | MockPool | OpenShiftProvisioning (K8s API) | OpenShiftValidation | OpenShiftCleanup | Working — tested on infra01 |
| RHDP | RHDPPool (Sandbox API) | RHDPProvisioning (AgnosticD) | RHDPValidation | RHDPCleanup (placement release) | Built — needs app token to test |

## Frontend Apps

| App | Tech | Status |
|-----|------|--------|
| Partner Portal | React/Vite/Tailwind | Done — branding, demos (18 items), sandbox config |
| Admin Dashboard | React/Vite/Tailwind | Done — sessions, tenants, catalog CRUD, system status |
| Demo Frontend | React/Vite/Tailwind | Done — runtime page filtering, 10 demo pages |

## Security

| Control | Status |
|---------|--------|
| SSO (oauth-proxy sidecar) | Done — Red Hat SSO on portal, admin, backend |
| API key auth (X-API-Key) | Done — regular + admin tiers |
| Session limits | Done — 2 per user, 5 per tenant (tested: 7 tests) |
| Resource quotas | Done — per-tier enforcement (light/medium/heavy) |
| LiteLLM virtual keys | Done — per-tenant, 7-day duration, model-scoped |
| Network policies | Done — egress + ingress in Helm chart |
| PSS restricted profile | Done — applied via namespace labels |
| Credential scrubbing | Done — maas_key nulled, plan scrubbed on reclaim |
| Kubeconfig (not --token) | Done — temp kubeconfig files, cleaned up after use |
| Public session view | Done — hides maas_api_key from non-admin |
| No hardcoded secrets | Verified — all secrets via env vars or CHANGE-ME templates |

## Testing

| Layer | Tests | Status |
|-------|-------|--------|
| Unit tests (Launchpad) | 406 | All pass |
| Lifecycle matrix | 54 | All 17 valid + 29 invalid transitions |
| Edge cases | 29 | Input validation, state, TTL, cleanup, API |
| Session limits | 7 | User + tenant limits, reclaim frees slots |
| Evidence bundles | 9 | StarGate payload format validated |
| RHDP adapters | 29 | Sandbox API client, pool, provisioning |
| Cleanup hardening | 12 | TTL, credentials, force_reclaim, audit |
| OpenShift cleanup | 8 | Gateway lock, timeout, RoleBinding |
| StarGate integration | 7 | Callback, constraint adapter |
| StarGate remediation (StarGate repo) | 11 | Catalog entries, risk, commands |
| Local E2E | 28 | Real containers, real inference |
| Cluster E2E (infra01) | 14/17 | 3 expected failures (need demo images) |
| **Total** | **462** | |

## CI/CD Gating

| Gate | Launchpad | StarGate |
|------|-----------|----------|
| Tests on push/PR | GitHub Actions | GitHub Actions |
| Lint (ruff) | On push/PR | — |
| TypeScript check | 3 apps on push/PR | N/A |
| Helm validation | 10 demos on push/PR | N/A |
| Image build verification | On push/PR | — |
| Remediation catalog validation | N/A | On push/PR |
| Manual deploy approval | workflow_dispatch | — |

## StarGate Integration

| Integration Point | Direction | Status |
|---|---|---|
| Pre-flight check | Launchpad → StarGate | Built + tested |
| Lifecycle evidence | Launchpad → StarGate | Built + tested (9 payload tests) |
| Cleanup callback | StarGate → Launchpad | Built + tested |
| Remediation catalog | StarGate | 3 entries + 11 tests |
| Graceful degradation | Both | Falls back when other is down |

## What's Left

| Priority | Item | Blocker |
|----------|------|---------|
| 1 | Sandbox API `app` role token | Need admin to issue |
| 2 | quay.io push access (`rhpds` org) | Need org admin |
| 3 | AgnosticV PR review | Tony Kay / Nate Stephany |
| 4 | Push container images | Needs #2 |
| 5 | End-to-end placement test | Needs #1 |
| 6 | Onboard Launchpad base cluster | Needs RHDP catalog entry |
| 7 | Showroom screenshots | Need running demo |
| 8 | AAP Job Template integration | Phase 2 |
| 9 | AI-powered brand generation | Future |
| 9 | AI-powered brand generation | Future |
