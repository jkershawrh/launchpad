# Launchpad YAML cleanup plan

## Purpose

Prepare the Intel-facing configuration for a slow, controlled rollout without
changing the active Launchpad service or treating all YAML in the repository as
one cleanup target. This plan is planning authority only: it does not authorize
deletion, credential rotation, catalog activation, GitOps sync, deployment, or
reclaim.

The repository currently contains **383 tracked YAML/YML files**. The largest
groups are `deploy/` (165), `demos/` (110), fixtures (20), evidence (18),
contracts (12), and catalog definitions (11). Cleanup must distinguish reusable
source, environment overlays, test fixtures, historical evidence, and obsolete
material before changing any file.

## Required scope decision

Before implementation, confirm with P. Davis which repository, branch, and YAML
paths are meant by “those yamls.” Record the answer as `YAML-SCOPE-001` with:

- accountable owner and approver;
- Intel handoff or publication destination;
- included and excluded paths;
- required environments and supported clusters;
- whether internal hostnames and branded assets may remain;
- retention requirements for historical evidence and pilot manifests;
- live GitOps applications that consume each included path.

No file may be deleted or moved until this scope record is approved. In
particular, `deploy/agnosticv/`, pilot evidence, catalog fixtures, and
environment overlays are not presumed obsolete.

## Current discovery status

YC-01 discovery has begun with a generated, privacy-safe inventory:

- [`yaml-inventory-v1.md`](yaml-inventory-v1.md) provides the human summary and
  bounded review queues.
- [`../evidence/yaml-cleanup/inventory-v1.json`](../evidence/yaml-cleanup/inventory-v1.json)
  is the machine-readable path, hash, classification, kind, reference, and risk
  metadata.

All records remain `preserve-pending-owner-review`. The inventory does not
complete YC-01 because owner assignment, external consumer confirmation, and
the approved Intel path scope remain outstanding.

Initial read-only results at the working-tree snapshot:

- 383 tracked YAML/YML files were inventoried; 173 have no repository reference
  detected and therefore require external-consumer review rather than deletion.
- All 14 tracked Kustomize roots under `deploy/` rendered locally without
  changing a cluster.
- Six source files contain Secret objects requiring classification. The full
  repository gitleaks scan passed, but that does not establish whether every
  template value is appropriate for an Intel handoff.
- Nineteen source files contain a mutable `latest` image reference. The Arena
  overlay currently renders two `ose-oauth-proxy:latest` references; these are
  pinning candidates, not authorization to change the running proxy.
- One Helm template contains possible cluster-export metadata and 36 documents
  contain a `status` field. Each requires semantic review because these may be
  legitimate application fields rather than Kubernetes runtime residue.

## Work packages

### YC-01 — Build a YAML ownership and consumption inventory

For every included file, record:

- purpose and owning component;
- owner and secondary reviewer;
- source, generated, fixture, evidence, or rendered-output classification;
- consuming application, build, test, script, or documentation;
- environment and cluster applicability;
- last meaningful change and last observed use;
- replacement or canonical source, if duplicated;
- proposed disposition: keep, normalize, move, archive, replace, or delete.

Use Git history, Kustomize references, Argo CD application sources, CI paths,
catalog loaders, and deployment scripts as evidence. Filename age alone is not
evidence that a manifest is unused.

**Exit gate:** every in-scope YAML has an owner, consumer, classification, and
proposed disposition; every deletion candidate has a proved replacement or
proved absence of consumers.

### YC-02 — Security and information-boundary review

Scan the working tree and Git history for:

- passwords, tokens, API keys, kubeconfigs, private keys, certificates, and
  populated Kubernetes Secrets;
- participant email, claim codes, tenant identifiers, and event-specific data;
- internal IP addresses, private registry credentials, unsupported hostnames,
  and personal paths;
- overly broad service accounts, RoleBindings, ClusterRoles, and wildcard RBAC;
- untrusted images, mutable tags, missing provenance, and unbounded pull
  behavior.

Do not place real credentials in replacement examples. Move runtime secrets to
approved secret references and synthetic placeholders. Any confirmed exposed
credential requires an owner-approved rotation plan; deleting it from the
current revision is not sufficient remediation.

**Exit gate:** secret and sensitive-data scans are clean for the proposed
handoff tree; RBAC findings have owners; history findings have an approved
retain, rotate, or history-remediation decision.

### YC-03 — Normalize source structure

Establish these boundaries:

- reusable Kubernetes resources in a neutral base;
- Arena, Brutus, Flightpath, Oberon, and future-home settings in explicit
  overlays;
- generated or rendered output outside authoritative source paths;
- catalog metadata separate from workload manifests;
- fixtures and synthetic examples clearly labeled and excluded from production
  application paths;
- dated evidence retained as immutable evidence, not copied into deployable
  overlays;
- deprecated integrations isolated until their owner approves archival.

Remove copied runtime metadata such as `resourceVersion`, `uid`,
`managedFields`, `creationTimestamp`, and Kubernetes `status` only where those
fields are actual cluster exports. Do not remove a domain-level `status` field
from a catalog, contract, fixture, or evidence document merely because it has
the same name.

**Exit gate:** there is one documented authority for each deployable object;
environment differences are overlays or values rather than copy-and-edit
forks; generated resources cannot be mistaken for source.

### YC-04 — Make manifests deterministic and portable

- Pin deployable images to approved immutable digests.
- Version APIs, catalog schemas, and contract schemas.
- Add consistent ownership, component, environment, cluster, and lifecycle
  labels where applicable.
- Replace hardcoded environment values with explicit configuration contracts.
- Declare storage, ingress, model, architecture, and operator prerequisites.
- Fail closed when a required Secret, cluster capability, or model endpoint is
  absent.
- Preserve environment-specific route and certificate configuration only in
  the appropriate overlay.

**Exit gate:** clean rendering produces deterministic output for every
supported overlay, and a missing prerequisite produces a clear validation
failure rather than a partially working deployment.

### YC-05 — Prove behavior before removal

For each proposed cleanup batch:

1. Capture the current rendered resources and consumer graph.
2. Write a failing regression for the defect or ambiguity being removed.
3. Apply the smallest source change.
4. Render and validate all affected overlays.
5. Compare resource identities, selectors, routes, RBAC, storage, images, and
   deletion behavior against the approved intent.
6. Deploy only to a disposable certification namespace or cluster.
7. Run create, readiness, participant journey, model call where applicable,
   expiration, reclaim, and zero-residue checks.
8. Prove rollback using the prior immutable revision.

Active retained labs are excluded from cleanup testing. No cleanup branch may
become a live GitOps source until the convergence owner approves its evidence.

**Exit gate:** TDD, EDD, CDD, BDD, and CBT are GREEN-integration for the batch;
the deployment and rollback use the same immutable artifacts that were tested.

### YC-06 — Intel handoff package

Produce a bounded handoff containing:

- the approved YAML tree and dependency lock or image digest list;
- supported-cluster and infrastructure prerequisites;
- configuration and secret-reference guide;
- clean install, validation, rollback, and uninstall instructions;
- architecture and ownership map;
- security, license, provenance, and known-risk evidence;
- exact rendered diff from the approved source revision;
- explicit exclusions and deferred work.

**Exit gate:** a qualified person who did not author the cleanup can deploy,
validate, roll back, and remove the package without personal credentials or
undocumented cluster knowledge.

## Proof matrix

| Area | TDD | EDD | CDD | BDD | CBT |
|---|---|---|---|---|---|
| Inventory and consumer graph | broken-reference regression | ownership and reference report | source/overlay classification | reviewer can trace an object to its consumer | inventory scanner |
| Secrets and RBAC | seeded-secret and privilege tests | signed scan reports and findings | secret-reference and RBAC policy | unauthorized identity is denied | scanner and policy engine |
| Rendering and portability | invalid-overlay regression | hashes and rendered diffs | base/overlay and prerequisite schemas | clean target renders or fails closed | renderer/validator |
| Deployment lifecycle | install/upgrade/reclaim regressions | session, resource, and cleanup receipts | lifecycle and catalog contracts | non-author completes the journey | cluster adapter and controllers |
| Rollback and removal | rollback/residue regressions | immutable before/after evidence | release identity contract | operator restores prior version | GitOps, registry, and cluster boundaries |

No critical matrix cell may be skipped. A file-count reduction is not a success
measure; the outcome is a smaller, understandable, reproducible, secure, and
supportable source of truth.

## Proposed sequence and elapsed time

This is a **five-business-day planning target** once scope and owners are
available. It may run in parallel with product development because no live
mutation is permitted from this stream.

1. **Day 1 — Scope and inventory:** approve `YAML-SCOPE-001`; generate the
   ownership and consumer inventory.
2. **Day 2 — Security and duplication review:** classify findings, identify
   rotations, and freeze deletion candidates.
3. **Day 3 — Proposed source layout:** produce move/keep/archive decisions and
   rendered before/after comparisons without deploying.
4. **Day 4 — Disposable proof:** validate the first bounded Intel handoff batch
   in a certification environment and prove rollback.
5. **Day 5 — Independent handoff review:** non-author walkthrough, evidence
   review, disposition approval, and merge recommendation.

Broader repository cleanup follows in separately reviewable batches. It must
not be folded into the Intel handoff merely to reduce file count.

## Roles and decisions needed Monday

- **Product/architecture owner:** approves scope and canonical source.
- **Intel project owner:** approves what may be handed off and the supported
  deployment boundary.
- **Security owner:** accepts secret, RBAC, provenance, and history decisions.
- **Platform/SRE owner:** validates install, rollback, cleanup, and support.
- **Content/catalog owners:** decide which demos, fixtures, and historical
  integrations remain supported.
- **Convergence owner:** is the only role permitted to request a live promotion.

Monday’s management discussion should identify these roles, confirm the slow
roll, and decide whether the first deliverable is an internal Intel package, a
portable enterprise package, or preparation for a future OSS boundary.

## Stop point

Planning stops with this document. The current platform, retained labs, Argo CD
applications, secrets, YAML files, and running resources remain unchanged.
Implementation begins only after `YAML-SCOPE-001` is approved.
