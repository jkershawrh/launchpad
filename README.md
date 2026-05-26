# Intel x Red Hat AI Partner Launchpad

![CI](https://github.com/rhpds/launchpad/actions/workflows/ci.yml/badge.svg)

Self-service demo platform that provisions AI lab environments on Red Hat OpenShift, powered by Intel Gaudi 3 accelerators and Xeon 6 processors. Integrates with the Red Hat Demo Platform (RHDP) to deliver repeatable, branded, time-boxed AI experiences for partners, customers, and internal teams.

Part of the **Launchpad + StarGate + DeepField** platform — three separate products that integrate via webhook events. Launchpad is the provisioning and demo plane.

## What It Does

One-click access to pre-built AI demos running on real hardware. Each demo provisions an isolated environment with its own namespace, inference gateway, model routing, and LiteLLM virtual API key — backed by Intel Gaudi 3 for accelerated inference and Intel Xeon 6 for CPU-optimized workloads.

**10 custom demos** built by the Intel x Red Hat partnership:

| Demo | What It Shows |
|------|--------------|
| **Inference Overdrive** | Real-time model routing across 5 models — compare Gaudi vs Xeon latency and throughput |
| **Enterprise RAG** | Retrieval-augmented generation with vector search, embedding on Xeon, generation on Gaudi |
| **Agent Swarm** | Multi-agent parallel execution — multiple models coordinate on complex tasks |
| **Research Agent** | Multi-step document analysis with query decomposition, reranking, and citations |
| **AIOps Copilot** | Alert classification, root cause analysis, and governance-gated remediation |
| **Governed Agent** | Risk-gated AI agent execution with policy enforcement and audit logging |
| **Hardware Recovery** | Graceful failover from Gaudi to CPU — transparent to the caller |
| **Workload Generator** | Load testing with storm, barrage, and token-cannon modes |
| **Model Training** | Fine-tuning workflows on Intel Gaudi with evaluation |
| **Replay Comparison** | Side-by-side Xeon vs Gaudi performance benchmarking |

**7 official Red Hat AI Quickstarts** from Summit, deployed via existing RHDP catalog items:

- Enterprise RAG Chatbot
- Data Governance
- PPE Compliance Monitor
- Product Recommendation
- IT Self-Service
- LLM CPU Serving (Intel Xeon)
- vLLM Tool Calling (Granite 3.2)

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  User                                                        │
│    │                                                         │
│    ▼                                                         │
│  RHDP Catalog (demo.redhat.com)                              │
│    │                                                         │
│    ▼                                                         │
│  Sandbox API ──► Assigns namespace on shared CNV cluster     │
│    │                                                         │
│    ▼                                                         │
│  AgnosticD ──► Deploys tenant via ArgoCD                     │
│    │                                                         │
│    ▼                                                         │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Per-Tenant Namespace                                  │  │
│  │  ┌──────────────┐  ┌────────────┐  ┌──────────────┐   │  │
│  │  │ Demo Frontend │  │  Gateway   │  │  PostgreSQL  │   │  │
│  │  │ (filtered     │─▶│ (routing   │  │  (state)     │   │  │
│  │  │  pages)       │  │  policy)   │  └──────────────┘   │  │
│  │  └──────────────┘  └─────┬──────┘                      │  │
│  └──────────────────────────┼─────────────────────────────┘  │
│                             │                                │
│                             ▼                                │
│                    LiteMaaS (LiteLLM)                        │
│                             │                                │
│              ┌──────────────┼──────────────┐                 │
│              ▼              ▼              ▼                 │
│         Intel Gaudi 3  Intel Xeon 6   llama.cpp              │
│         (Granite, Phi, (embeddings,   (Llama 70B)            │
│          DeepSeek,      classification)                      │
│          Qwen)                                               │
└──────────────────────────────────────────────────────────────┘
```

### Key Components

| Component | Purpose |
|-----------|---------|
| **Sandbox API** | RHDP cluster pool manager — assigns namespaces on shared OpenShift clusters |
| **AgnosticD** | Ansible-based deployment automation — installs operators and workloads |
| **ArgoCD** | GitOps delivery — deploys the tenant Helm chart per user |
| **Inference Gateway** | FastAPI service implementing model routing policy across Intel hardware |
| **LiteMaaS** | LiteLLM proxy providing unified OpenAI-compatible API across all models |
| **Showroom** | Interactive lab UI with step-by-step instructions, terminal, and console tabs |
| **Demo Frontend** | React application with runtime page filtering via ConfigMap |

## How It Works

### For Users

1. Order a demo from the RHDP catalog at demo.redhat.com
2. Receive a Showroom URL with SSO credentials
3. Follow the step-by-step lab instructions in the left panel
4. Interact with the demo in the right panel (terminal, console, or demo portal)
5. Environment automatically reclaims after the configured TTL

### For Operators

1. The **cluster config** (`launchpad-cluster`) provisions shared base infrastructure once — RHOAI, GitOps, Keycloak on a CNV pool cluster
2. Each **tenant config** (`launchpad-*-tenant`) creates an isolated per-user environment on the shared cluster
3. The Sandbox API manages capacity, quotas, and lifecycle
4. Each tenant gets its own LiteLLM virtual key for usage tracking and rate limiting

## Platform Integration

Launchpad integrates with StarGate (validation) and DeepField (fleet monitoring) via webhook events. All integrations fail silently when targets are not configured.

```
                    +-------------------+
                    |     DeepField     |   OBSERVABILITY
                    | Fleet signal intel|
                    +--------+----------+
                             |
                  monitors clusters that
                  Launchpad provisions on
                             |
+------------------+    +----v----------------+
|    StarGate      |    | Launchpad (you)     |   PROVISIONING + DEMOS
| Rubric evaluator |<-->| 17-state lifecycle  |
| Evidence bundles |    | Inference gateway   |
| Failure classes  |    | Workshop batching   |
+------------------+    +---------------------+
```

| Direction | What | Trigger |
|-----------|------|---------|
| Launchpad → StarGate | Lifecycle events (session provisioned, failed, reclaimed) | Every session state transition |
| Launchpad → StarGate | Pre-flight check before provisioning | Before each provision |
| Launchpad → DeepField | Same lifecycle events (parallel push) | Every session state transition |
| StarGate → Launchpad | Cleanup results after remediation | `POST /callbacks/cleanup-result` |
| DeepField → Launchpad | Remediation suggestions | `POST /callbacks/remediation` |

### Integration Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `STARGATE_API_URL` | No | StarGate base URL. Falls back to no-op if not set. |
| `STARGATE_API_KEY` | No | API key for StarGate authentication. |
| `STARGATE_SSL_VERIFY` | No | Set to `false` to skip TLS verification. Default: `true`. |
| `DEEPFIELD_API_URL` | No | DeepField base URL for pushing lifecycle events. |
| `DEEPFIELD_API_KEY` | No | API key for DeepField authentication. |

## Tech Stack

- **Backend:** Python >=3.11, FastAPI >=0.115, Pydantic >=2.10, asyncpg >=0.30
- **Database:** PostgreSQL via asyncpg (with in-memory fallback for testing)
- **Frontends:** React 19, Vite 8, TypeScript 6 — Tailwind (portal/admin) + PatternFly (demos)
- **API prefix:** All routes under `/api/v1/` (integration routes under `/integration/`)
- **Deployment:** AgnosticD + ArgoCD, Kustomize manifests, UBI9 containers, Podman

## Repository Structure

```
launchpad/
├── backend/                    # FastAPI backend — lifecycle, provisioning, adapters
│   └── app/
│       ├── adapters/           # Mock, local, OpenShift, and RHDP adapter tiers
│       │   └── rhdp/           # Sandbox API client and RHDP provisioning
│       ├── domain/             # Pydantic models, enums, state machine
│       ├── services/           # Provisioning service, lifecycle management
│       └── api/                # REST API endpoints
├── frontend/                   # Partner portal (React/Vite/Tailwind)
├── admin/                      # Admin dashboard (React/Vite/Tailwind)
├── demos/
│   ├── frontend/               # Demo frontend (React, runtime page filtering)
│   └── gateway/                # Inference gateway (FastAPI, routing policy)
├── content/                    # Showroom lab content (Antora/AsciiDoc)
│   └── modules/ROOT/pages/     # 12 lab guide pages
├── tenant/
│   └── bootstrap/              # Helm chart deployed per-user by ArgoCD
├── deploy/
│   ├── agnosticv/              # RHDP catalog item configs (cluster + tenant)
│   └── launchpad/              # Kustomize manifests for Launchpad platform
└── docs/                       # Architecture and process documentation
```

## Models

All models served via KServe on OpenShift AI, accessed through LiteMaaS:

| Model | Hardware | Use Case |
|-------|----------|----------|
| Granite 3.2 8B Instruct | Intel Gaudi 3 | General-purpose generation, classification |
| Llama 3.1 70B | CPU (llama.cpp) | Large-scale reasoning |
| DeepSeek R1 Distill Qwen 14B | Intel Gaudi 3 | Deep reasoning, chain-of-thought |
| Microsoft Phi-4 | Intel Gaudi 3 | Efficient small-model inference |
| Qwen3 14B | Intel Gaudi 3 | Multilingual generation, tool calling |

## Infrastructure

- **Compute:** Intel Gaudi 3 (24 cards across 3 nodes) + Intel Xeon 6
- **Platform:** Red Hat OpenShift 4.18+ with OpenShift AI 2.25
- **Cluster pools:** Managed by RHDP Sandbox API across CNV clusters
- **Deployment:** AgnosticD + ArgoCD (GitOps)
- **Auth:** Keycloak SSO + LiteLLM virtual keys per tenant

## Roadmap

### Done

- [x] Backend — FastAPI with domain models, lifecycle state machine, adapter pattern (mock/local/openshift/rhdp)
- [x] Partner portal — React frontend with branding, demo catalog, sandbox configuration
- [x] Admin dashboard — session management, tenant management, catalog CRUD, system status, Official badges, RHDP column
- [x] Demo frontend — runtime page filtering via ConfigMap, 10 demo pages
- [x] Inference gateway — FastAPI routing policy across Gaudi/Xeon/CPU backends
- [x] RHDP Sandbox API integration — client, pool adapter, provisioning adapter, cleanup
- [x] Catalog — 25 items (10 custom demos, 7 official quickstarts, 4 sandboxes, 4 originals), all wired to RHDP
- [x] AgnosticV configs — cluster config + 11 tenant configs following RHDP pattern, PR submitted to `rhpds/agnosticv`
- [x] Tenant bootstrap Helm chart — ArgoCD-deployable (frontend + gateway + postgres + route + NetworkPolicy)
- [x] Per-demo model lists — each demo gets LiteLLM virtual keys for 1-5 models based on routing needs
- [x] Showroom lab content — 12 AsciiDoc pages with step-by-step walkthroughs matching RHDP quickstart format
- [x] Sandbox API verified — connected to real fleet (10 CNV clusters), login + cluster listing working
- [x] Container images built locally — `launchpad-demo-frontend` (363 MB) + `launchpad-gateway` (2.25 GB)
- [x] Workshop batch provisioning — Workshop model, `POST/GET/DELETE /api/workshops`, bulk provision/reclaim N sessions (TDD)
- [x] Persistent demos — `persistence: persistent` → never expires, `reinitialize` resets without destroying (TDD)
- [x] Labels — `launchpad.redhat.com/tenant`, `session-id`, `catalog-item`, `purpose`, `workshop-id` on all resources (TDD)
- [x] Security hardening — PSS restricted on namespaces, egress/ingress NetworkPolicy, random PG passwords, kubeconfig (not --token CLI args), public session view hides MaaS keys (TDD)
- [x] Cleanup hardening — TTL enforcement daemon, credential scrubbing on reclaim, force_reclaim calls cleanup adapter, workshop error tracking, gateway namespace lock, cleanup timeout fatal, orphaned RoleBinding cleanup, audit trail (TDD)
- [x] StarGate integration — pre-flight constraint adapter, cleanup callback endpoint, remediation catalog entries in StarGate repo, graceful degradation when StarGate is down (TDD)
- [x] Cleanup hardening — TTL enforcement, credential scrubbing, force_reclaim cleanup, workshop error tracking, gateway lock, timeout fatal, orphaned RoleBinding cleanup, audit trail (TDD)
- [x] StarGate integration — pre-flight constraint adapter, cleanup callback endpoint, remediation catalog entries in StarGate repo, graceful degradation (TDD)
- [x] Edge case coverage — input validation, state edge cases, TTL boundaries, workshop boundaries, cleanup edge cases, credential edge cases, API error handling (TDD)
- [x] Comprehensive test matrix — lifecycle state matrix (54 tests), session limits (7), evidence bundles (9), duplicates (3), edge cases (29)
- [x] CI/CD gating — GitHub Actions: tests + lint on push/PR, TypeScript check, Helm validation, image build verification, manual deploy approval
- [x] Admin persistent demos tab — uptime, reset button, cleanup_failed tracking
- [x] AAP URL wiring (Phase 1) — aap_url populated from env var in sandbox provisioning
- [x] Live E2E test scripts — `scripts/live-e2e-test.sh` (28/28 local), `scripts/cluster-e2e-test.sh` (14/17 infra01)
- [x] Test receipt system — JSON receipts with timestamps, commit hashes, per-test results in `test-receipts/`
- [x] Repo live — https://github.com/rhpds/launchpad
- [x] 420 backend tests passing — all features TDD red/green
- [x] 11 StarGate remediation tests — catalog entries validated
- [x] 8 AAP client tests — job template launch, poll, wait, error handling
- [x] 6 AI brand generation tests — LLM-powered branding with graceful fallback
- [x] GitHub Actions CI green — tests, lint, TypeScript, Helm, image builds on every push
- [x] Security hardened — API keys rotated, git history scrubbed, secret scanning + push protection enabled
- [x] Documentation — architecture, adapters, build matrix, provisioning lifecycle, tenancy, showback all current

### Waiting On (external)

- [ ] Sandbox API `app` role token — need admin to run `sandbox-cli jwt issue --name launchpad --role app`
- [ ] quay.io push access — need to be added to `rhpds` org to push container images
- [ ] AgnosticV PR review — submitted to `rhpds/agnosticv` branch `launchpad-demos`, pending review from Tony Kay / Nate Stephany

### To Do (once unblocked)

- [ ] Push container images to `quay.io/rhpds/launchpad-demo-frontend` and `quay.io/rhpds/launchpad-gateway`
- [ ] End-to-end placement test — create a real namespace on a CNV cluster via Sandbox API
- [ ] Onboard a Launchpad base cluster — order `launchpad-cluster` from RHDP to provision shared infra
- [ ] Full end-to-end test — order a demo from RHDP catalog, verify Showroom + frontend + gateway + inference
- [ ] Showroom screenshots — capture from a running demo environment
- [ ] AAP Job Template provisioning — wire AAPClient into provisioning adapter (client built, needs job templates on AAP controller)
- [ ] AI brand generation on live LLM — BrandGenerator built, needs LiteMaaS endpoint configured

## Development

```bash
# Run locally with mock adapters
cd backend
LAUNCHPAD_MODE=mock uvicorn app.main:app --reload

# Run tests
cd backend && python -m pytest tests/ -q

# Run with RHDP integration (requires VPN + Sandbox API token)
LAUNCHPAD_MODE=rhdp \
SANDBOX_API_URL=$SANDBOX_API_URL \
SANDBOX_LOGIN_TOKEN=$(cat ~/.sandbox/token) \
HTTPS_PROXY=$HTTPS_PROXY \
uvicorn app.main:app --reload
```
