# YAML source inventory v1

This is the generated discovery companion to
[`yaml-cleanup-plan.md`](yaml-cleanup-plan.md). It records paths, hashes,
classifications, kinds, repository references, and risk categories only. It
does **not** copy YAML values or authorize any cleanup action.

## Safety boundary

Discovery only. No record authorizes deletion, movement, secret rotation, deployment, GitOps sync, catalog activation, or live mutation.

An absent detected reference does not prove a file is unused. External GitOps,
CLI, documentation, and human consumers must be checked before disposition.

## Summary

- Tracked YAML/YML files: **383**
- Owner assignment still required: **383**
- Preserved pending owner review: **383**
- No repository reference detected: **173**
- Base source commit: `dbc47df1db3bc300100579d84197afb8cc4dc376`
- Source state: **working-tree**; tracked changes present:
  **true**

## Classification

| Classification | Files |
|---|---:|
| `catalog-source` | 11 |
| `ci` | 2 |
| `configuration` | 3 |
| `content-source` | 18 |
| `contract` | 12 |
| `demo-source` | 110 |
| `deployment-source` | 154 |
| `deployment-template` | 11 |
| `evidence` | 22 |
| `fixture` | 20 |
| `generated-intake` | 4 |
| `repository-configuration` | 6 |
| `tenant-source` | 10 |

## Review flags

Flags identify required review; they are not findings by themselves. For
example, a domain contract may legitimately contain a `status` field.

| Flag | Files |
|---|---:|
| `environment-specific` | 110 |
| `mutable-latest-image` | 19 |
| `possible-cluster-export-metadata` | 1 |
| `secret-object-review-required` | 6 |
| `status-field-review-required` | 36 |

## Priority review queues

These paths require classification, not automatic modification. Secret objects
may be safe templates, `latest` may be replaced by an overlay digest, and a
runtime-looking field may be legitimate application data.

### Secret objects

- `demos/deploy/cluster/secrets-template.yaml`
- `demos/deploy/database/secret.yaml`
- `deploy/launchpad/base/oauth-setup.yaml`
- `deploy/launchpad/base/secrets-template.yaml`
- `tenant/bootstrap/templates/gateway-secret.yaml`
- `tenant/bootstrap/templates/postgres-secret.yaml`

### Mutable `latest` image references

- `demos/deploy/cluster/frontend-deployment.yaml`
- `demos/deploy/cluster/frontend-simple-deployment.yaml`
- `demos/deploy/cluster/gateway-deployment.yaml`
- `demos/deploy/database/deployment.yaml`
- `demos/deploy/gateway/deployment.yaml`
- `demos/deploy/openvino-cpu/serving-runtime.yaml`
- `demos/deploy/pipelines/pipeline.yaml`
- `deploy/launchpad/base/admin-deployment.yaml`
- `deploy/launchpad/base/backend-deployment.yaml`
- `deploy/launchpad/base/lifecycle-scheduler-cronjob.yaml`
- `deploy/launchpad/base/lifecycle-worker-deployment.yaml`
- `deploy/launchpad/base/partner-portal-deployment.yaml`
- `deploy/launchpad/base/public-access-gateway.yaml`
- `deploy/launchpad/overlays/arena/operations-automation.yaml`
- `deploy/launchpad/overlays/oberon/operations-automation.yaml`
- `deploy/launchpad/public-access/keycloak-postgres.yaml`
- `deploy/launchpad/runbooks/intel-sep17-dayof.yaml`
- `tenant/bootstrap/templates/gateway-deployment.yaml`
- `tenant/bootstrap/values.yaml`

### Possible cluster-export metadata

- `deploy/workloads/agentops-seat/templates/grafana.yaml`

The complete machine-readable inventory is
[`../evidence/yaml-cleanup/inventory-v1.json`](../evidence/yaml-cleanup/inventory-v1.json).
