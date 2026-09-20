# Catalog onboarding pipeline

Launchpad catalog onboarding is Git-first and evidence-gated. A content
integrator declares a lab once in `catalog-onboarding/<catalog-id>.yaml`; the
pipeline renders and validates its draft catalog record, checks immutable
Showroom and workload sources, builds the Antora site, and emits a JSON receipt.

This removes the repeated hand-editing of catalog metadata, source revisions,
resource estimates, tab declarations, and certification gates. It does not
automatically make an untested lab orderable. Runtime integration and live
certification remain explicit promotion gates.

## Source-of-truth contract

Each intake declares:

- catalog ID, title, description, category, and version;
- immutable Showroom repository SHA, playbook, and Antora start path;
- immutable workload repository SHA, packaging type, and deployment path;
- deployment class: `shared_namespace` (default),
  `dedicated_workshop_cluster`, or exceptional `dedicated_seat_cluster`, with
  a learning-objective and isolation justification for either dedicated class;
- required cluster capabilities and models;
- supported platform architectures and versions, required Operators, storage,
  ingress, egress, and cluster-scoped mutations;
- immutable platform, Showroom, terminal, and workload image digests from the
  approved registry, plus signature/provenance policy and mirror requirements;
- conservative steady per-seat CPU, memory, pod, and storage estimates;
- optional per-seat transient CPU, memory, and pod costs, bounded by the
  declared workshop provisioning concurrency, plus optional workshop-shared
  resource costs;
- the complete participant tab contract;
- the current certification stage, supported seat ceiling, promotion sequence,
  every activation blocker, and an optional reusable proof-contract path.

The corresponding `catalog/<catalog-id>/catalog-item.yaml` is generated from
that contract. Intake-managed entries are always rendered as `draft`. Changing
them to `active` is a separate, reviewed promotion after the blockers are
cleared and the evidence has been accepted.

## Deployment-class and artifact review

The default onboarding outcome is a namespace-isolated seat on a warm
execution cluster. Reviewers select a dedicated workshop cluster only when the
lab requires cluster-scoped administration, destructive exercises, special
hardware/network/storage, regulated isolation, or a capacity envelope that
cannot safely coexist. A dedicated seat cluster requires the curriculum to
teach full-cluster behavior and must publish separate lead-time, cost, security,
and reclaim evidence.

Onboarding never treats cluster creation as a workaround for missing resource
estimates, RBAC, or cleanup. The certification matrix records the permitted
deployment class for every catalog × cluster × exposure-policy pairing.

Images follow one supply contract:

1. build reproducibly from the reviewed immutable source revision;
2. scan, produce an SBOM, sign, and attach provenance;
3. publish to the approved HA registry under an immutable digest;
4. promote the same digest without rebuilding;
5. verify credentials, trust, architecture, and cold pull on each eligible
   worker pool or synchronized mirror; and
6. retain the digest through every active session and rollback window.

Mutable tags may be human-friendly aliases but are never the deployed catalog
contract. An execution cluster's internal registry may be a cache or mirror;
it is not the authoritative or cross-cluster source.

### Authoritative registry status

`config/artifact-registry-policy.yaml` selects `quay.io/redhat-gpte` as the
provisional authoritative origin and reserves a dedicated repository for each
platform component. The policy is intentionally fail-closed: it does not make
a release production-eligible until organizational ownership, scoped robot
grants, signing identity, retention/restore, and per-cluster exact-digest cold
pull evidence are recorded. In particular, the Keycloak image must use its own
repository; temporarily storing a stage build in the backend repository is not
a promotable production pattern.

Run `make artifact-registry` for the local contract gate. Release automation
must additionally use `scripts/validate_artifact_registry.py
--require-release-ready`, which remains red until every integration and live
qualification is complete.

The destination qualification contract is versioned in
`contracts/artifact-destination-qualification-v1.yaml`. A destination receipt
must identify one immutable image from the authoritative origin and prove the
pull credential, registry certificate, architecture, signature, exact digest,
cold pull, and cache-loss paths. Each check requires its own evidence reference;
missing, failed, credential-bearing, mutable, wrong-origin, or unsupported-
architecture receipts are rejected as a whole. The evaluator is offline and
does not treat a synthetic receipt as live cluster qualification.

## Local workflow

### Start from an existing quickstart repository

The onboarding CLI can inspect an immutable quickstart revision and generate
the first fail-closed intake. It discovers a local Antora playbook/component
pair and a Helm, Kustomize, or manifest workload package. It also creates a
review-only repository inventory covering Containerfiles, image references,
Kubernetes resource kinds, Operators, ports, Routes, model-valued environment
variables, resource requests and limits, persistent storage, Secret references,
cluster-scoped resources, privileged behavior, and cleanup candidates.

Discovery records Secret names and reference locations only. It never copies
Secret `data` or `stringData` into the intake or discovery receipt. The
inventory is evidence for a reviewer, not an approval: it deliberately does
not infer supported resource sizing, models, participant tabs, identity,
runtime Secret delivery, cleanup safety, or certification results. Mutable
images, cluster-scoped resources, privileged behavior, repository-managed
Secret manifests, and manifests that cannot be parsed all add explicit
activation blockers.

Inspect a protected, clean local checkout whose `HEAD` equals the supplied SHA:

```bash
.venv/bin/python scripts/catalog_onboarding.py scaffold \
  --repo-url https://github.com/<owner>/<quickstart>.git \
  --revision <40-character-git-sha> \
  --catalog-id <catalog-id> \
  --display-name "<Display name>" \
  --source-dir /path/to/quickstart \
  --output catalog-onboarding/<catalog-id>.yaml \
  --report test-receipts/<catalog-id>-discovery.json
```

The discovery report uses the versioned
`launchpad.redhat.com/catalog-discovery-receipt/v1` contract and contains the
complete fail-closed draft input. Render the deterministic catalog draft from
that receipt:

```bash
.venv/bin/python scripts/catalog_onboarding.py draft \
  test-receipts/<catalog-id>-discovery.json \
  --output catalog/<catalog-id>/catalog-item.yaml
```

Draft generation validates that the receipt passed repository discovery, both
source revisions match the receipt's immutable Git SHA, the catalog identity
has not changed, the static inventory is unchanged, exposure remains
internal-only, the seat ceiling remains one, and at least one activation
blocker remains unresolved. A mismatch exits nonzero before writing the output.
Running the command repeatedly with the same receipt produces the same catalog
YAML.

This command creates a review artifact; it does not edit the live catalog,
approve a blocker, run a one-seat lifecycle, promote an image, or call an
execution cluster. Promotion remains a separate human-reviewed and
evidence-gated operation.

Omit `--source-dir` to fetch and verify the exact immutable revision in a
temporary checkout. The generated intake is `draft`, internal-only, limited to
one seat, and carries activation blockers. Its zero resource fields and default
terminal tab are visible placeholders that a content integrator must replace
with measured and reviewed contracts. Discovery fails nonzero when no valid
Antora source or deployable workload is found. Multiple candidates produce a
warning and block activation until the deterministic selection is reviewed.
Local discovery rejects a non-Git directory, a different `HEAD`, or uncommitted
changes so the receipt cannot describe content other than the declared SHA.

The static image inventory is intentionally separate from artifact promotion.
It identifies what the repository appears to reference and flags mutable
references. The authoritative registry, signing, SBOM, provenance, retention,
pull-grant, architecture, mirror, cold-pull, and rollback checks remain the
supply-chain promotion gate. Static discovery never marks an image approved or
deployable.

After review, commit the intake, render the catalog record, and use the existing
source/build/certification path below. There is one pipeline, not a per-lab
adapter or set of manual platform edits.

Render a catalog record:

```bash
.venv/bin/python scripts/catalog_onboarding.py render \
  catalog-onboarding/<catalog-id>.yaml \
  --output catalog/<catalog-id>/catalog-item.yaml
```

Validate local source checkouts:

```bash
.venv/bin/python scripts/catalog_onboarding.py validate \
  catalog-onboarding/<catalog-id>.yaml \
  --catalog catalog/<catalog-id>/catalog-item.yaml \
  --showroom-dir /path/to/showroom \
  --workload-dir /path/to/workload \
  --build-showroom \
  --antora-bin node_modules/.bin/antora
```

Validate the exact remote commits as CI does:

```bash
.venv/bin/python scripts/catalog_onboarding.py validate \
  catalog-onboarding/<catalog-id>.yaml \
  --catalog catalog/<catalog-id>/catalog-item.yaml \
  --fetch \
  --build-showroom \
  --antora-bin node_modules/.bin/antora \
  --report test-receipts/catalog-onboarding-<catalog-id>.json
```

The command exits nonzero for a malformed intake, mutable Git reference,
missing content/page/image, missing workload package, failed Antora build, or
catalog drift. An intact draft with declared activation blockers passes source
validation and reports `activation_status: blocked`; this is intentional.

## Pull-request automation

The `Catalog Onboarding Contracts` CI job discovers every YAML file under
`catalog-onboarding/`. For each intake it:

1. fetches the pinned Showroom and workload revisions;
2. validates Antora playbook, component, navigation, pages, and local images;
3. validates the declared Helm, Kustomize, or manifest package;
4. compares the generated record with the committed catalog YAML;
5. builds the complete Showroom through Antora; and
6. uploads a machine-readable validation receipt.

When an intake declares `certification.proof_contract`, CI also validates the
referenced `CatalogCertification` document. The proof contract must match the
catalog ID and promotion sequence, use repository-contained probe paths, avoid
shell command strings, define deterministic structural assertions, and carry a
100-point fail-closed rubric.

Adding another intake does not require a workflow change.

## Repeatable certification runner

The onboarding intake describes what Launchpad deploys. A corresponding file
under `certification/catalog/` describes how the deployed workshop is proven.
Multi-Agent Quickstart is the reference implementation.

Each proof contract declares:

- the single allowed execution cluster and exposure policies;
- 1-, 5-, and 25-seat profiles, time budgets, probe concurrency, and required
  consecutive passes;
- Showroom page paths and stable content markers;
- one argument-vector seat probe and structural JSON assertions;
- the complete label-scoped cleanup resource set; and
- a weighted release rubric totaling 100 points.

Generate a non-mutating plan:

```bash
.venv/bin/python scripts/catalog_certification.py plan \
  certification/catalog/<catalog-id>.yaml \
  --seats 5
```

Execute a live Arena proof only with credentials supplied through environment
variables:

```bash
KUBECONFIG=/path/to/arena-kubeconfig \
LAUNCHPAD_ADMIN_API_KEY='set-outside-git' \
.venv/bin/python scripts/catalog_certification.py run \
  certification/catalog/<catalog-id>.yaml \
  --seats 5 \
  --api-base-url https://launchpad-api.apps.arena.fm2aihpcsed.com \
  --tenant-id <certification-tenant> \
  --owner-id <operator> \
  --run-id <unique-proof-run>
```

The runner performs the capacity preview, creates exactly one workshop order,
persists one cluster assignment, waits until all seats are ready, and then
starts bounded concurrent participant probes. It always attempts group reclaim,
counts every labeled cleanup resource, verifies model-key revocation, scores the
rubric, and writes a sanitized evidence JSON file with a sibling SHA-256 file.

Model prose is intentionally excluded from exact comparisons. Lab probes assert
stable behavior such as response schema, agent sequence, tool use, routing,
guardrail decisions, authorization, and error counts. This keeps live proof
repeatable without replacing real inference with a mock.

## Promotion path

The automated source gate is only the first layer:

1. **Intake:** source and package checks pass; catalog remains `draft`.
2. **Runtime integration:** per-seat configuration, routes, secrets, labels,
   readiness, validation, and deterministic cleanup are implemented.
3. **One seat:** a participant completes the real journey and reclaim leaves no
   residue.
4. **Five seats:** concurrency, isolation, model behavior, and shared services
   are measured.
5. **Twenty-five seats:** the intended workshop envelope is certified with
   participant-facing, performance, failure-recovery, and cleanup evidence.
6. **Activation:** reviewers remove resolved blockers, update measured resource
   values and certification stage, and explicitly promote the catalog item.

The repeatable handoff from a quickstart repository is therefore:

```text
immutable repo -> discover/scaffold -> reviewed intake -> rendered catalog
-> source and Antora validation -> runtime integration -> 1/5/25 proof
-> explicit promotion -> supported use -> zero-residue reclaim
```

Large labs may stop at a lower certified seat ceiling. The catalog must publish
the measured safe limit rather than copying the platform-wide maximum.

Capacity contracts distinguish three resource classes:

- `seat_resources` are present for every active participant seat;
- `transient_seat_resources` exist only while a seat is provisioning and are
  reserved for at most `workshop_provision_concurrency` seats at once; and
- `workshop_shared_resources` are created once for the whole order.

When the optional resource classes are omitted, Launchpad retains the original
per-seat multiplication. A capacity preview returns the total reservation and
the shared, steady per-seat, and bounded-transient breakdown. This prevents a
short rollout burst from being multiplied across every seat while still
failing closed when that burst cannot fit.

## Multi-Agent Quickstart intake status

`multi-agent-quickstart` is registered as a distinct draft candidate from
`jkershawrh/multi-agent-quickstart` at
`243870fa4675987bf77c310a53deee672a4f4af2`. Its Launchpad-native Antora
journey is pinned at `pilot-2026-09-17-showroom-multi-agent-v1.0.3` and covers
A2A discovery, semantic routing, MCP tool calls, guardrails, OpenTelemetry,
namespace isolation, and customization.

Revision `243870fa4675987bf77c310a53deee672a4f4af2` also exposes ordered workflow
progress so Research, Analyst, and Executor results appear when each dependent
stage completes, plus bounded seat-browser run history. The matching Showroom
content calls the contract-advertised MCP tool `search_knowledge_base`.

The Launchpad seat chart now deploys the orchestrator, three agents, MCP server,
guardrails, and Gradio UI with a runtime Secret and complete ownership labels.
One clean Arena seat, all three Showroom tracks, a five-seat workshop, and three
consecutive 25-seat workshops are GREEN-live. The catalog is certified for up
to 25 internal Arena seats while durable image supply, public access, and the
optional Track 3 runtime integrations remain fail-closed. See
[multi-agent-quickstart-import.md](multi-agent-quickstart-import.md).

## AgentOps intake status

The detailed RHDP topology and Launchpad adaptation decisions are recorded in
[agentops-rhdp-gap-analysis.md](agentops-rhdp-gap-analysis.md).

`agentops-observability` is registered as a draft candidate from:

- Launchpad Showroom: `rhpds/launchpad`,
  `content-agentops-observability`, at
  `59563b0a77252e8b91077c30c23ab524a8402bce`;
- upstream Showroom provenance: `rhpds/agentops-intel-showroom` at
  `f1881c61de55ebf5640c27e76469f4efe458edaf`;
- Launchpad seat chart: `rhpds/launchpad`, `deploy/workloads/agentops-seat`, at
  `8596c9e979c76562b5e1239eec2c96e15305568b`;
- referenced RHDP automation: `rhpds/agentops-in-prod-automation` at
  `6ea100531ac869fa66abe69ae223d6b56dbce9a2`;
- transitive Mortgage AI application: `rh-ai-quickstart/multi-agent-loan-origination`
  at `1e50e51c334c1b6ed854d81a3f28fd324792f481`.

The RHDP deployment path was also traced through AgnosticV
`agd_v2/agentops-intel` at
`48fc6eebedb295bddf1b915a230e5e90f89db0af`. That configuration does not
deploy the application chart directly. It runs the bootstrap chart from
`rhpds/agentops-in-prod-automation` at
`6ea100531ac869fa66abe69ae223d6b56dbce9a2`. That repository is retained as
immutable provenance, but it is not Launchpad's deployable workload source.
The deployable source is the Launchpad-owned namespace-scoped seat chart at
`8596c9e979c76562b5e1239eec2c96e15305568b`. The application repository remains
recorded as transitive source provenance.

Its source and Antora build pass. The Launchpad-owned component replaces the
fixed RHDP username/password and `wksp-user1` namespace with participant SSO
and generated seat values, pins the PatternFly 6 UI and application sources,
and describes the Arena `granite-3.2-8b-tools` target. The upstream screenshots
and instructional flow remain attributed at their immutable revision.

It is not orderable because the complete live experience still requires the
pre-provisioned mortgage application, shared MLflow, per-seat Grafana,
OpenShift Logging, user workload monitoring, OpenShift AI workbenches and
pipelines, and eight authorized environment tabs.

The RHDP automation is a workshop-scoped app-of-apps. It installs cluster-global
Applications named `mlflow`, `logging`, `cluster-monitoring`, `image-puller`,
and `openshift-ai`, then uses ApplicationSets for each `wksp-userN` namespace.
Those global names make the unmodified bootstrap unsafe for concurrent
Launchpad orders. Launchpad installs compatible shared Arena services once and
generates only uniquely owned, namespace-scoped seat resources per order.
The current AgnosticV catalog declares `num_users: 1` and
`workshop_user_mode: single`; 5- and 25-seat use is a new Launchpad
certification target, not a capability inherited from the RHDP item.
The upstream bootstrap also places the LiteMaaS virtual key in Helm values,
which would expose it in the Argo CD Application. The Launchpad adapter now
creates an idempotent runtime Secret directly through the Arena API and passes
only the Secret name to Argo CD. Generated database and object-storage
passwords, the LiteMaaS endpoint/key, requested model, and composed connection
URLs are resolved without serializing secret values in Git or the Application.
The chart also receives workshop, seat, session, tenant, and cluster identity
values and labels every resource with them.

The chart renders no Secret or cluster-scoped resource. An Arena server-side
dry run accepted all 21 rendered resources. The least-privilege rule in
`deploy/multicluster/arena-argocd-rbac.yaml` is applied: Arena verifies that the
remote Argo service account can create namespaced `ServiceMonitor` and DSPA
resources but cannot create cluster roles.

The repository now contains roughly 34 MiB of instructional images. The
adapted playbook uses the pinned PatternFly 6 Showroom theme; content delivery
therefore uses the same immutable Git-first path as the other Launchpad labs.

The namespace-scoped workload is now `gitops_ready: true`, while the catalog
item remains `draft` and capped at five internal seats. Arena now provides a functional
shared MLflow service backed by persistent PostgreSQL with verified OpenShift
service-ca TLS, plus a supported OpenShift Logging 6.6 one-seat pilot. The
participant can query application logs in the assigned namespace and is denied
access to another namespace. A Launchpad-created internal order has proven the
runtime Secret, workload Application, protected routes, Showroom, complete
participant journey, and zero-residue reclaim together. A five-seat run also
proved isolated concurrent journeys and cleanup. The seat chart now co-locates
the Mortgage API and UI without merging their Services or routes, reducing the
measured steady topology from 13 to 12 pods per seat. Four rollout/bootstrap
pods remain a bounded transient cost for each of the two concurrently
provisioned seats. Per-seat DSPA and database instances remain isolated because
sharing a project-scoped RHOAI pipeline service would change the participant
security boundary. The 25-seat gate still requires measured live capacity,
durable S3-compatible object storage, dynamic block storage, and a
production-sized Loki topology.
