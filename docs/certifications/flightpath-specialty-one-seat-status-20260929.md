# Flightpath specialty one-seat certification status — updated October 1, 2026

## Decision

Five specialty catalog items have completed one-seat Flightpath proof and
normal reclaim. One remains internal-only. Four items completed the
full external `public_code` journey and may be presented as public one-seat
releases. No result below authorizes more than one seat.

| Catalog item | One-seat result | Participant journey | Reclaim | Current exposure contract | Promotion state |
| --- | --- | --- | --- | --- | --- |
| `virtualization-ai-foundations-101` | GREEN-live on Flightpath | LIVE Intel Xeon inference; VM ready; terminal scoped to the seat namespace; own-namespace edit allowed; cross-namespace and node access denied | Normal reclaim; zero namespace and Argo CD Application residue | `internal` | Internal proof complete; public promotion not requested or proven |
| `virtualization-ai-201` | GREEN-live on Flightpath | Trusted external TLS; email-and-code claim and same-seat recovery; Showroom, Story, Terminal, ready contract-author VM, live Intel Xeon inference, namespace isolation, and the authored contract journey passed | Normal reclaim; identity disabled, model key revoked, idempotent reclaim, and zero namespaces, Applications, Routes, RoleBindings, Secrets, or active entitlements | `internal`, `public_code` | Public one-seat certified; active and capped at one seat |
| `sovereign-ai-201` | GREEN-live on Flightpath | Trusted external TLS; email-and-code claim and same-seat recovery; Showroom, Story, Terminal, live governed-boundary journey, Intel Xeon model contract, namespace isolation, and fail-closed behavior passed | Normal reclaim; identity disabled, model key revoked, idempotent reclaim, and zero namespaces, Applications, Routes, RoleBindings, Secrets, or active entitlements | `internal`, `public_code` | Public one-seat certified; active and capped at one seat |
| `sovereign-ai-101` | GREEN-live on Flightpath | Trusted external TLS; email-and-code claim; same-seat recovery; landing, Showroom, declared tools, logout and resume; own-namespace edit allowed and cross-namespace access denied | Normal reclaim; identity disabled, model key revoked, and zero namespaces, Applications, Routes, RoleBindings, Secrets, or active entitlements | `internal`, `public_code` | Public one-seat certified; active and capped at one seat |
| `virtualization-ai-301` | GREEN-live on Flightpath | Trusted external TLS; email-and-code claim; same-seat recovery; corrected Story and Terminal journeys; own-namespace edit allowed; cross-namespace and cluster-scoped node access denied | Normal reclaim; identity disabled, model key revoked, and zero namespaces, Applications, Routes, RoleBindings, Secrets, or active entitlements | `internal`, `public_code` | Public one-seat certified; active and capped at one seat |

The original internal three-item baseline is Launchpad commit `a89d7c4`. Sovereign AI
101 retains its September 29 public proof. Virtualization AI 301 was
re-certified on October 1 at Launchpad commit `2bd00ad`, backend image
`quay.io/rh-ee-jkershaw/launchpad-backend@sha256:e35bd0a68d6aad7d09eb11ccdad1c8672b5229a27f4d904d8735b5acb850e028`,
and exact content commit `30f51e19223faf64c689a07e254870fbc43fd0c6`.
Sovereign AI 201 was publicly certified on October 1 at Launchpad commit
`6c32049` and exact content commit
`0fdcfba6c2db35190a768e561ac6b0665c76484b`.
Virtualization AI 201 was publicly certified on October 1 at Launchpad commit
`3bd40b7` and exact content commit
`3c94600ca8808a55693e94d5a1f169efbadbedd1`.
Runtime and content dependencies remain digest- or commit-pinned in the
corresponding catalog packages.

## Evidence accounting

The remaining internal-only certification output still requires conversion
to one immutable, hashed evidence manifest per catalog item. Their correct roadmap
state remains:

- implementation and live-cluster behavior: **GREEN-live (internal)**;
- durable EDD package: **open**;
- external participant behavior: **RED / not run**;
- public catalog promotion: **blocked**.

Sovereign AI 101, Sovereign AI 201, Virtualization AI 201, and Virtualization
AI 301 have immutable public evidence:

- `evidence/runs/catalog/sovereign-ai-101-flightpath-public-one-seat-20260929-r1.json`
- `evidence/runs/catalog/sovereign-ai-201-flightpath-public-one-seat-20261001-r1.json`
- `evidence/runs/catalog/virtualization-ai-201-flightpath-public-one-seat-20261001-r1.json`
- `evidence/runs/catalog/virtualization-ai-301-flightpath-public-one-seat-20261001-r2.json`

All four manifests have verified SHA-256 sidecars, record a 100-point passing
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
Sovereign AI 101, Sovereign AI 201, Virtualization AI 201, and Virtualization
AI 301 only. Virtualization Foundations 101 remains internal until separately
promoted and certified.

## Metadata reconciliation still required

The remaining internal-only catalog files may still contain pre-certification
activation wording. Reconcile it only when writing their immutable internal
manifests and making an explicit promotion decision. Sovereign AI 101,
Sovereign AI 201, Virtualization AI 201, and Virtualization AI 301 already have empty activation
blockers and truthful one-seat public metadata. Do not silently remove remaining public, scale,
security, or artifact-retention gates from any other item.
