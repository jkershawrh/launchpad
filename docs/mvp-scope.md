# MVP Scope

## What's IN

### Catalog (21 items)

| Category | Count | Examples |
|----------|-------|---------|
| Quick Starts | 8 | Inference Overdrive, Enterprise RAG, AIOps Copilot, Recovery Demo, Replay Comparison, RAG Chatbot QS, LLM CPU Serving QS, vLLM Tool Calling QS |
| Guided Builds | 5 | Governed Agent, Agent Swarm, Research Agent, Workload Generator, Training Demo |
| Open Sandboxes | 8 | Mixed AI Sandbox, Full Platform Sandbox, Minimal/AI Dev/Full Stack/Custom Sandbox, plus original |

### Demo Separation

Each demo runs in its own namespace with its own filtered frontend. Demos within a tenant share an inference gateway.

### Sandbox

Pod-based sandboxes with three stack levels (minimal, ai_dev, full_redhat_ai), five access methods (SSH, Jupyter, VS Code, web console, API), and configurable AAP integration levels.

### MaaS Inference

LiteLLM-compatible gateway with intelligent routing across three backends (OpenVINO-CPU, vLLM-CPU, vLLM-Gaudi). Per-session API keys. Cost-per-token tracking.

### SSO

OAuth integration stub with Keycloak realm configuration. Token-based session authentication.

### Persistence

PostgreSQL storage for sessions, requests, and plans. Sessions survive backend restarts. Orphaned session cleanup on startup.

### Admin

Admin dashboard with sessions by tenant, showback summaries, active labs, failed validations, expiring labs. Force-reclaim capability.

### Reports

Handoff packages (Markdown + JSON), showback records, repeatability reports, security plans.

## What's Intentionally OUT

| Feature | Why it's out |
|---------|-------------|
| **Multi-cluster support** | MVP targets a single OCP cluster. Multi-cluster routing adds complexity without MVP value. |
| **Real billing/chargeback** | Showback tracks usage metadata. Real cost calculation and invoicing are deferred. |
| **Production-grade auth** | OAuth stub exists. Full RBAC, group sync, and IdP federation are post-MVP. |
| **AI brand generation** | BrandingProfile is config-driven. AI-generated logos/themes are future. |
| **Real Babylon/Pool Boy/Anarchy Gov** | Adapter interfaces defined, mock implementations used. Real integration awaits API availability. |
| **Autonomous AI provisioning** | AutomationGenerator interface exists. AI-generated manifests require proposal-first review flow. |
| **Complex approval workflows** | Constraint adapter returns allowed/blocked. Multi-step approval chains are deferred. |
| **Live Gaudi allocation** | Hardware profiles model Gaudi access. Direct device scheduling is post-MVP. |

## What's Next

| Priority | Item | Description |
|----------|------|-------------|
| 1 | **RHOAI install patterns** | Operator-based OpenShift AI deployment as a catalog item |
| 2 | **Official quickstarts deployment** | Helm/kustomize provisioners deploying the 3 official Red Hat AI quickstarts to live clusters |
| 3 | **StarGate patterns** | Integration patterns for StarGate workloads on the same infrastructure |
| 4 | **Real Prometheus observability** | Replace mock metrics with live scraping from namespace-scoped Prometheus |
| 5 | **Babylon/Pool Boy integration** | Connect to real catalog and pool APIs when available |
| 6 | **OCP Virt isolation** | VM-level isolation for high-security tenants |
