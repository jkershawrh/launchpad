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

## Models (via LiteMaaS on ocp-rac-maas)

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
| ocp-rac-maas | Model serving (Gaudi 3 + Xeon 6) | Running — 5 models, RHOAI 2.25 |
| ocpv-infra01 | Launchpad platform (backend, portal, admin) | Running — 4 pods |
| CNV pool (ocpv01-10) | Demo deployment targets via Sandbox API | 10 clusters, 8 valid |
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
| Session limits | Done — 2 per user, 5 per tenant |
| Resource quotas | Done — per-tier enforcement (light/medium/heavy) |
| LiteLLM virtual keys | Done — per-tenant, 7-day duration, model-scoped |
| Network policies | Done — namespace isolation |
| No hardcoded secrets | Verified — all secrets via env vars or CHANGE-ME templates |

## What's Left

| Priority | Item | Blocker |
|----------|------|---------|
| 1 | `app` role Sandbox API token | Need admin to issue |
| 2 | Build + push container images | Need quay.io push access |
| 3 | End-to-end placement test | Needs #1 |
| 4 | Submit AgnosticV configs to `rhpds/agnosticv` | PR |
| 5 | Onboard Launchpad base cluster | Needs RHDP catalog entry |
| 6 | RHOAI install on infra01 | Manager approval |
| 7 | Showroom screenshots | Need running demo for captures |
| 8 | Admin dashboard — 4 new quickstarts | Small update |
| 9 | AI-powered brand generation | Future |
