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

- Tracked YAML/YML files: **481**
- Owner assignment still required: **0**
- Preserved pending owner review: **481**
- Deletion eligible: **0**
- No repository reference detected: **185**
- Base source commit: `376ebda5e853edcfa81389ec8510efc13e97d1bc`
- Source state: **working-tree**; tracked changes present:
  **true**

## Classification

| Classification | Files |
|---|---:|
| `catalog-source` | 14 |
| `ci` | 4 |
| `configuration` | 11 |
| `content-source` | 18 |
| `contract` | 48 |
| `demo-source` | 110 |
| `deployment-source` | 194 |
| `deployment-template` | 11 |
| `evidence` | 26 |
| `fixture` | 20 |
| `generated-intake` | 7 |
| `repository-configuration` | 8 |
| `tenant-source` | 10 |

## Review flags

Flags identify required review; they are not findings by themselves. For
example, a domain contract may legitimately contain a `status` field.

| Flag | Files |
|---|---:|
| `environment-specific` | 164 |
| `mutable-latest-image` | 19 |
| `possible-cluster-export-metadata` | 1 |
| `secret-object-review-required` | 6 |
| `status-field-review-required` | 71 |

## Red Hat-hosted and RHDP dependency review

These counts identify YAML files with explicit external Git, image, or
automation references. They do not expose URL values and do not imply that a
reference should be removed. The approved RHPDS Launchpad repository and
Showroom content may remain; use the flags to prove portability and identify
hidden RHDP/AgnosticD requirements. Inspect the machine-readable records and
prove each active consumer before changing it.

| Dependency | Files |
|---|---:|
| `agnostic-automation-dependency` | 29 |
| `redhat-gpte-image-dependency` | 10 |
| `rhdp-service-dependency` | 2 |
| `rhpds-git-dependency` | 38 |
| `rhpds-image-dependency` | 14 |

## Protection classes

Every tracked YAML file remains deletion-ineligible until `YAML-SCOPE-001` is
approved and its external consumers are checked. Role ownership below routes
review; it is not named-human acceptance.

| Protection class | Files |
|---|---:|
| `authoritative-contract` | 48 |
| `catalog-release-input` | 21 |
| `external-consumer-unknown` | 37 |
| `immutable-evidence` | 26 |
| `participant-content-input` | 128 |
| `repository-governance-input` | 8 |
| `runtime-or-deployment-input` | 189 |
| `test-or-delivery-input` | 24 |

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
