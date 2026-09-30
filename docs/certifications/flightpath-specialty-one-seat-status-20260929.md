# Flightpath specialty one-seat certification status — September 29, 2026

## Decision

Five specialty catalog items have completed one-seat Flightpath proof and
normal reclaim. Three remain internal-only. Two additional items completed the
full external `public_code` journey and may be presented as public one-seat
releases. No result below authorizes more than one seat.

| Catalog item | One-seat result | Participant journey | Reclaim | Current exposure contract | Promotion state |
| --- | --- | --- | --- | --- | --- |
| `virtualization-ai-foundations-101` | GREEN-live on Flightpath | LIVE Intel Xeon inference; VM ready; terminal scoped to the seat namespace; own-namespace edit allowed; cross-namespace and node access denied | Normal reclaim; zero namespace and Argo CD Application residue | `internal` | Internal proof complete; public promotion not requested or proven |
| `virtualization-ai-201` | GREEN-live on Flightpath | Showroom, presentation, adapter, VM readiness, namespace isolation, and the authored contract journey passed; rehearsal labeling retained where the journey intentionally uses deterministic evidence | Normal reclaim; zero namespace and Argo CD Application residue | `internal` | Internal proof complete; external gate open |
| `sovereign-ai-201` | GREEN-live on Flightpath | Showroom, presentation, adapter, governed-boundary journey, model contract, namespace isolation, and fail-closed behavior passed | Normal reclaim; zero namespace and Argo CD Application residue | `internal` | Internal proof complete; external gate open |
| `sovereign-ai-101` | GREEN-live on Flightpath | Trusted external TLS; email-and-code claim; same-seat recovery; landing, Showroom, declared tools, logout and resume; own-namespace edit allowed and cross-namespace access denied | Normal reclaim; identity disabled, model key revoked, and zero namespaces, Applications, Routes, RoleBindings, Secrets, or active entitlements | `internal`, `public_code` | Public one-seat certified; active and capped at one seat |
| `virtualization-ai-301` | GREEN-live on Flightpath | Trusted external TLS; email-and-code claim; same-seat recovery; corrected Story and Terminal journeys; own-namespace edit allowed; cross-namespace and cluster-scoped node access denied | Normal reclaim; identity disabled, model key revoked, and zero namespaces, Applications, Routes, RoleBindings, Secrets, or active entitlements | `internal`, `public_code` | Public one-seat certified; active and capped at one seat |

The internal three-item baseline is Launchpad commit `a89d7c4`. The public
two-item baseline is Launchpad commit `599c551`, backend image
`ghcr.io/rhpds/launchpad-backend@sha256:8a5c588cc01007bc2e0307cbe9669cc3e008dc0d4973ccb51d28eb191b106e55`,
with the Virtualization 301 content correction at commit `9ffe5eb`. Runtime and
content dependencies are digest- or commit-pinned in the corresponding catalog
packages.

## Evidence accounting

The original three internal certification outputs still require conversion to
one immutable, hashed evidence manifest per catalog item. Their correct roadmap
state remains:

- implementation and live-cluster behavior: **GREEN-live (internal)**;
- durable EDD package: **open**;
- external participant behavior: **RED / not run**;
- public catalog promotion: **blocked**.

Sovereign AI 101 and Virtualization AI 301 have immutable public evidence:

- `evidence/runs/catalog/sovereign-ai-101-flightpath-public-one-seat-20260929-r1.json`
- `evidence/runs/catalog/virtualization-ai-301-flightpath-public-one-seat-20260929-r1.json`

Both manifests have verified SHA-256 sidecars, record a 100-point passing
rubric, contain no plaintext credentials or participant email export, and end
with zero counted residue.

This distinction prevents a successful internal operator canary from being
mistaken for email-and-code participant proof.

## Exact external/public promotion gate

For each catalog item intentionally offered publicly, all of the following must
pass against one unchanged Flightpath candidate and one seat:

1. **Catalog admission** — explicitly add `public_code` to
   `allowed_exposure_policies`, retain the one-seat ceiling, and prove the
   requester and backend report the same orderability and capacity decision.
2. **Public origin** — the stable public URL resolves externally, presents a
   trusted certificate, and reaches only the approved gateway paths.
3. **Order secret** — the requester receives the instructor code once; only its
   hash is persisted; the plaintext code is absent from logs and evidence.
4. **Participant claim** — a clean external-browser session claims the seat
   with email plus code, receives the expected opaque participant identity,
   and a repeated claim recovers the same seat rather than consuming another.
5. **Participant navigation** — participant landing, My Lab Access, Open Lab,
   Showroom/instructions, presentation or story, terminal, workspace, and the
   namespace-scoped OpenShift Console all load through the supported public
   origin without a redirect loop, recursive iframe, `403`, `404`, or `500`.
6. **Authorization boundary** — the participant can modify only the assigned
   namespace; another namespace and cluster-scoped nodes remain denied. Direct
   seat routes and private model, API, admin, database, and Argo CD endpoints
   remain inaccessible.
7. **Journey truthfulness** — LIVE and REHEARSAL data are labeled accurately;
   required model calls succeed where the catalog contract requires them; no
   rehearsal response is recorded as live inference.
8. **Session behavior** — resume, add-lab, logout, expired/invalid code denial,
   and code rotation/reauthentication behave according to the public-access
   contract. A single-seat certification may use a second temporary order to
   prove add-lab without increasing either catalog's seat ceiling.
9. **Lifecycle and cleanup** — normal reclaim revokes access and removes the
   namespace, Routes, RoleBindings, Argo CD Applications, entitlements,
   credentials, and inactive participant identity. Reclaim is repeated once to
   prove idempotency and leaves zero residue.
10. **Immutable evidence** — capture commit and image identities, catalog
    version, cluster, order/session/seat identifiers, timestamps, HTTP/TLS and
    authorization results, audit events, screenshots or browser assertions,
    cleanup counts, and artifact hashes in the evidence tree.

Only after every row is green should another catalog item move from
`draft`/internal-only to public orderability. This gate is complete for
Sovereign AI 101 and Virtualization AI 301 only. Virtualization Foundations
101, Virtualization 201, and Sovereign AI 201 remain internal until separately
promoted and certified.

## Metadata reconciliation still required

The three internal-only catalog files may still contain pre-certification
activation wording. Reconcile it only when writing their immutable internal
manifests and making an explicit promotion decision. Sovereign AI 101 and
Virtualization AI 301 already have empty activation blockers and truthful
one-seat public metadata. Do not silently remove remaining public, scale,
security, or artifact-retention gates from any other item.
