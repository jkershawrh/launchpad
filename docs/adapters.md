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

## Mock Adapters (Testing)

Located in `backend/app/adapters/mock/`. Used for unit tests, integration tests, and local demo mode.

| Adapter | What it does |
|---------|-------------|
| `MockCatalogAdapter` | Serves 21 seed catalog items from in-memory list |
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

Located in `backend/app/adapters/openshift/`. Used on live OCP clusters.

| Adapter | What it does |
|---------|-------------|
| `OpenShiftSandboxProvisioner` | Creates namespace, applies quota/RBAC/NetworkPolicy, deploys Pod with SSH |
| OpenShift provisioning | Creates namespaces, applies kustomize/helm manifests via Kubernetes API |
| OpenShift cleanup | Deletes namespaces and associated resources |
| OpenShift validation | Checks pod readiness, route accessibility, service endpoints |

## Sandbox Provisioner (Pod-Based)

Sandbox sessions run as Pods (or local containers) with configurable stack levels:

| Stack Level | Packages |
|-------------|----------|
| `minimal` | python3.11, oc, podman, git, vim |
| `ai_dev` | + pytorch, vllm, jupyter, ansible-navigator, huggingface-cli |
| `full_redhat_ai` | + openvino, intel-extension-for-pytorch, kafka-client, tekton-cli, helm |

Access methods: SSH (2222), Jupyter (8888), VS Code Server (8443), Web Console (6901), API (8080).

## Future Integration Points

| System | Adapter role | Status |
|--------|-------------|--------|
| **Babylon** | CatalogAdapter — pull catalog items from Babylon catalog | Not yet integrated |
| **Pool Boy** | PoolAdapter — real resource pool capacity and reservation | Not yet integrated |
| **Anarchy Gov** | ConstraintAdapter — governance policy evaluation | Not yet integrated |
| **AAP** | ProvisioningAdapter — execute Ansible playbooks for setup | Interface defined |
| **GitOps** | ProvisioningAdapter — apply manifests via ArgoCD/Flux | Interface defined |
| **Tekton** | ProvisioningAdapter — run pipelines for complex provisioning | Interface defined |
