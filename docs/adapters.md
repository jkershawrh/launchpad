# Adapters

## Adapter Interfaces

All adapter interfaces are defined as Python `Protocol` classes in `backend/app/adapters/interfaces.py`.

| Interface | Methods | Purpose |
|-----------|---------|---------|
| `CatalogAdapter` | `list_items`, `get_item`, `validate_item` | Catalog item storage and lookup |
| `PoolAdapter` | `check_capacity`, `reserve`, `release`, `report_allocation` | Resource pool management |
| `ConstraintAdapter` | `evaluate` | Policy evaluation (allowed / warn / blocked) |
| `ProvisioningAdapter` | `create_plan`, `provision` | Plan generation and environment creation |
| `ValidationAdapter` | `validate` | Post-provisioning health checks |
| `ObservabilityAdapter` | `create_dashboard`, `get_metrics`, `get_health` | Dashboard and metrics |
| `ShowbackAdapter` | `create_record`, `summarize`, `export_report` | Usage tracking and reporting |
| `BrandingAdapter` | `load_profile`, `list_profiles` | Visual identity management |
| `AutomationGenerator` | `generate` | AI-generated AAP/OpenShift artifacts (future) |

## Adapter Tiers

| Tier | `LAUNCHPAD_MODE` | When to use |
|------|-----------------|-------------|
| Mock | `mock` (default) | Unit/integration tests, local demo |
| Local | `local` | Podman-compose on developer laptop |
| OpenShift | `openshift` | Direct deployment on a live OCP cluster via Kubernetes API |
| RHDP | `rhdp` | Red Hat Demo Platform — Sandbox API for cluster pool, AgnosticD for deployment |

## Mock Adapters (Testing)

Located in `backend/app/adapters/mock/`. Used for unit tests, integration tests, and local demo mode.

| Adapter | What it does |
|---------|-------------|
| `MockCatalogAdapter` | Serves 25 seed catalog items from in-memory list |
| `MockPoolAdapter` | Always has capacity, tracks reservations in a dict |
| `MockConstraintAdapter` | Always returns `allowed` |
| `MockProvisioningAdapter` | Generates namespace and URLs without creating real resources |
| `MockValidationAdapter` | Returns all-pass results |
| `MockObservabilityAdapter` | Returns placeholder dashboard URL |
| `MockShowbackAdapter` | Generates record from session metadata |
| `FileBrandingAdapter` | Loads branding profiles from YAML fixtures |
| `DemoProvisioningAdapter` | Creates plans with gateway configuration for demo catalog items |
| `DemoValidationAdapter` | Validates gateway health, demo source existence, config validity |

## Local Adapters (Podman-Compose)

Located in `backend/app/adapters/local/`. Used for running real containers on a developer laptop.

| Adapter | What it does |
|---------|-------------|
| `LocalSandboxProvisioner` | Builds sandbox container image, runs it via podman, waits for SSH |
| Local provisioning | Deploys via podman-compose with gateway + frontend + database |
| Local cleanup | Stops and removes containers by name |
| Local validation | Health-checks running containers via HTTP/SSH probes |

## OpenShift Adapters (Kubernetes API + oc CLI)

Located in `backend/app/adapters/openshift/`. Used on live OCP clusters for direct namespace-level deployment.

| Adapter | What it does |
|---------|-------------|
| `OpenShiftSandboxProvisioner` | Creates namespace, applies quota/RBAC/NetworkPolicy, deploys Pod with SSH |
| OpenShift provisioning | Creates namespaces, applies kustomize/helm manifests via Kubernetes API |
| OpenShift cleanup | Deletes namespaces and associated resources |
| OpenShift validation | Checks pod readiness, route accessibility, service endpoints |

## RHDP Adapters (Sandbox API + AgnosticD)

Located in `backend/app/adapters/rhdp/`. Used for Red Hat Demo Platform integration — claims namespaces from the RHDP cluster pool and deploys workloads via AgnosticD/ArgoCD.

| Adapter | What it does |
|---------|-------------|
| `SandboxAPIClient` | Full client for the RHDP Sandbox API — JWT auth, placements CRUD, cluster config, sandbox accounts |
| `RHDPPoolAdapter` | Claims/releases namespaces on shared CNV clusters via the Sandbox API |
| `RHDPProvisioningAdapter` | Creates provisioning plans referencing AgnosticV configs; deploys via ArgoCD or direct oc/helm |
| `RHDPValidationAdapter` | Validates sandbox placement exists, namespace assigned, lab URL set |
| `RHDPCleanupAdapter` | Releases Sandbox API placements on session reclaim |

### Sandbox API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/login` | Exchange login JWT for access token |
| `POST /api/v1/placements` | Create a tenant placement (namespace on shared cluster) |
| `GET /api/v1/placements/<uuid>` | Poll placement status until `success` |
| `DELETE /api/v1/placements/<uuid>` | Release a placement |
| `POST /api/v1/ocp-shared-cluster-configurations` | Register a cluster (admin) |
| `GET /api/v1/accounts/OcpSandbox` | List sandbox accounts |

### Hybrid Provisioner Routing

When `LAUNCHPAD_MODE=rhdp`, the provisioning service checks each catalog item's `provisioner_mode` metadata. Items with `provisioner_mode: "rhdp"` route to `RHDPProvisioningAdapter`; others use the default provisioner. This allows mixed mode — official quickstarts use RHDP while sandboxes use direct OpenShift provisioning.

## Sandbox Provisioner (Pod-Based)

Sandbox sessions run as Pods (or local containers) with configurable stack levels:

| Stack Level | Packages |
|-------------|----------|
| `minimal` | python3.11, oc, podman, git, vim |
| `ai_dev` | + pytorch, vllm, jupyter, ansible-navigator, huggingface-cli |
| `full_redhat_ai` | + openvino, intel-extension-for-pytorch, kafka-client, tekton-cli, helm |

Access methods: SSH (2222), Jupyter (8888), VS Code Server (8443), Web Console (6901), API (8080).

## Integration Status

| System | Adapter role | Status |
|--------|-------------|--------|
| **RHDP Sandbox API** | PoolAdapter — claims namespaces from cluster pool | Integrated — client built, API verified |
| **AgnosticD** | ProvisioningAdapter — deploys workloads via Ansible/ArgoCD | Configs written — 11 tenant configs in `deploy/agnosticv/` |
| **ArgoCD** | Tenant deployment — Helm chart at `tenant/bootstrap/` | Built — parameterized by demo type |
| **LiteMaaS** | Model access — LiteLLM virtual keys per tenant | Integrated — 5 models on Gaudi 3 |
| **Showroom** | Lab UI — interactive instructions with terminal + console | Content written — 12 AsciiDoc pages |
| **AAP** | ProvisioningAdapter — execute Ansible playbooks for setup | Interface defined, not yet integrated |
| **Tekton** | ProvisioningAdapter — run pipelines for complex provisioning | Interface defined, not yet integrated |
