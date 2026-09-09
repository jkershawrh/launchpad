---
marp: true
theme: uncover
paginate: true
backgroundColor: #0A1628
color: #E8F0FE
style: |
  section { font-family: Arial, Helvetica, sans-serif; padding: 58px 72px; }
  h1 { color: #FFFFFF; font-size: 42px; }
  h2 { color: #5CC8FF; }
  strong { color: #FFFFFF; }
  table { font-size: 21px; }
  th { color: #5CC8FF; }
  code { background: #142A43; color: #FFFFFF; }
  pre { background: #142A43; border: 1px solid #244866; color: #E8F0FE; font-size: 20px; }
  pre code { background: transparent; color: #E8F0FE; }
  blockquote { border-left: 6px solid #EE0000; color: #FFFFFF; }
  section.compact { font-size: 24px; }
  section.compact table { font-size: 18px; }
  section.compact pre { font-size: 17px; }
  .eyebrow { color: #5CC8FF; font-size: 18px; letter-spacing: 0.14em; text-transform: uppercase; }
  .status { color: #66D9A4; }
  .pending { color: #FFCA58; }
  .muted { color: #AFC3D8; }
  .logos { display: flex; gap: 38px; justify-content: center; align-items: center; margin-top: 34px; }
  .logos > img { max-height: 58px; max-width: 190px; }
  .redhat-lockup { display: inline-flex; gap: 12px; align-items: center; color: #FFFFFF; font-size: 28px; font-weight: 700; }
  .redhat-lockup img { height: 52px; width: auto; }
---

<!-- _class: lead -->

<div class="eyebrow">Distributed AI workshop operations</div>

# Intel × Red Hat AI Launchpad

### Order once. Learn in isolation. Reclaim completely.

<div class="logos">
  <img src="../../demos/frontend/public/intel-logo.svg" alt="Intel">
  <span class="redhat-lockup"><img src="../../frontend/public/logos/redhat.svg" alt="">Red Hat</span>
</div>

<!--
Open with the operational problem, not the implementation. Launchpad turns a
versioned lab into a repeatable distributed workshop lifecycle. This is a
supervised internal pilot, not a GA announcement.
-->

---

# The operating problem

One workshop is more than a set of pods.

- **Content** must match the deployed workload
- **25 identities** need isolated, usable environments
- **Placement** must respect real cluster capacity
- **Model and operator access** must work for participants
- **Reclaim** must remove every owned artifact

> The product is the complete order-to-zero-residue lifecycle.

<!--
Stress that pod readiness is not success. The learner journey, authorization,
evidence, and cleanup are part of the product contract.
-->

---

# Pilot proof: three workshops, 75 participants

| Workshop | Execution cluster | Result |
|---|---|---:|
| Building an AI Agent | Brutus | **25 / 25** |
| Build Multi-Agent AI Systems | Arena | **25 / 25** |
| Serve LLMs on Intel Xeon | Arena | **25 / 25** |

**Staggered provisioning. Concurrent use. Zero-residue group reclaim.**

<span class="status">GREEN-live automated pilot gate</span><br>
<span class="pending">Manual visual and public-access gates remain separate</span>

<!--
Use the exact language: three orders were staggered, then all 75 participant
environments ran together. Do not claim one arbitrary 75-seat workshop fits one
cluster or that the service is production certified.
-->

---

<!-- _class: compact -->

# One control plane, distributed execution

```text
                  Requester / Instructor / Participant
                                 │
                     Arena Launchpad entry point
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
        Lifecycle + DB      Arena Argo CD     Admin + evidence
              │                  │
         whole-order         destination
          placement            sync
              │                  │
          ┌───┴────┐        ┌────┴────┐
          │ Arena  │        │ Brutus │
          └────────┘        └────────┘
```

**Oberon:** excluded pending cluster remediation<br>
**Flightpath:** passive DR candidate, not an active writer

<!--
Arena owns the current control plane. A single entry point does not mean one
execution cluster. Placement is persisted before any seat resource is created.
-->

---

<!-- _class: compact -->

# The lifecycle is the contract

```text
Git intent → preview → reserve → persist cluster_ref → provision
                                                     ↓
zero residue ← release ← reclaim ← use ← handoff ← validate
```

- One workshop stays on **one eligible cluster**
- Capacity is reserved for the **complete order**
- Participant behavior—not pod status—decides readiness
- Retry and cleanup stay on the persisted `cluster_ref`
- Reclaim is idempotent and ends with an explicit residue check

<!--
If the whole workshop cannot fit, Launchpad rejects before creating seats. It
never silently splits an order or retries cleanup against a different cluster.
-->

---

# The participant experience

**Open Lab** provides one guided seat experience:

1. Version-pinned Showroom learning journey
2. Terminal already scoped to the assigned namespace
3. Operator and application tools embedded for the lab
4. Real catalog-specific agent or model exercise
5. Namespace authorization with cross-seat denial

The participant should not need to understand cluster placement to learn.

<!--
During the demo, prove oc project, a permitted namespaced action, a denied
cross-namespace action, and one real application/agent/model result.
-->

---

# Live demo path

| Minute | Show | Prove |
|---:|---|---|
| 0–4 | Catalog and 25-seat request | Versioned intent and one-order model |
| 4–7 | Capacity and placement | Complete-order fit and persisted target |
| 7–10 | Admin operations | Order, cluster, seat, and failure visibility |
| 10–15 | Participant lab | Content, terminal scope, operator/app workflow |
| 15–18 | Architecture and evidence | Distributed execution with one entry point |
| 18–20 | Group reclaim | Terminal state and zero residue |

<!--
Use docs/presenter-demo-walkthrough.md for preflight, exact operator cues,
fallbacks, and the closing talk track.
-->

---

<!-- _class: compact -->

# Evidence is part of delivery

Every certification run records:

- commit SHA, image digests, and catalog version
- order, seat, namespace, tenant, and cluster correlation
- capacity, readiness, function, isolation, and timing results
- audit and lifecycle events
- group reclaim and zero-residue counts
- artifact hashes and a scored release rubric

**RED stays immutable. GREEN must point to proof.**

<!--
This is the EDD portion of the delivery model. Defects first become a failing
regression test; no evidence is replaced simply because a later run passes.
-->

---

# Scale by measured graduation

| Gate | Scale | Decision |
|---|---:|---|
| Source and component | local | structure, security, deterministic contract |
| First participant | 1 | complete learner journey and cleanup |
| Concurrency | 5 | isolation, shared services, model behavior |
| Workshop | 25 | readiness SLO, functional load, bulk reclaim |
| Larger workshop | 50 → 75 | only after node and headroom proof |
| Fleet | multiple orders | queue fairness and failure-domain rehearsal |

> Never publish a seat limit from allocatable capacity alone.

<!--
The current event proof is three 25-seat orders across Arena and Brutus. A
single-cluster 50- or 75-seat claim remains a future certification gate.
-->

---

# The operations intelligence loop

```text
DeepField signals ─┐
                   ├→ StarGate failure class → GCL or GeoLux proposal
Launchpad evidence ┘                              │
                                                  ▼
                     Launchpad policy → operator approval
                              │              or allow-list
                              ▼
                   persisted-cluster executor
                              │
                    post-action validation
```

**Launchpad remains the lifecycle mutation authority.**

<!--
DeepField provides fleet/network/inference signals. StarGate normalizes
preflight and failure evidence. GCL or GeoLux is a future governed decision
provider, not a second provisioner. The selection is intentionally unresolved.
-->

---

<!-- _class: compact -->

# Autonomy has a safety ladder

1. **Observe** — attach evidence; operator uses the runbook
2. **Recommend** — show one bounded action and affected resources
3. **Approve** — authenticated, idempotent execution
4. **Automatic** — allow-listed, retry-budgeted, validated, circuit-broken

Start with validation retry, Showroom resync, owned Route reconciliation,
managed-workload restart, expiry, reclaim retry, and stale-record repair.

<span class="pending">RBAC, Secrets, Operators, nodes, storage, DNS, models, and
cross-cluster migration always require human authority.</span>

<!--
Do not imply current autonomous remediation. The integrations are a graduated
roadmap and every failure class earns its own promotion.
-->

---

# Onboard a quickstart without bespoke platform edits

```text
immutable quickstart repo
          ↓ discover
fail-closed intake + discovery receipt
          ↓ review
catalog + Showroom + workload contract
          ↓ prove
source build → 1 seat → 5 seats → 25 seats
          ↓ approve
orderable catalog → supported use → reclaim
```

Git remains the source of truth. Promotion remains explicit.

<!--
Demonstrate scripts/catalog_onboarding.py scaffold. It discovers Antora and
Helm/Kustomize/manifests, but never guesses models, resources, identity, tabs,
or certification results.
-->

---

<!-- _class: compact -->

# Deploy the ecosystem to another cluster

The portable playbooks enforce a repeatable path:

- read-only API, node, storage, and credential preflight
- server-side apply of the reviewed control-plane overlay
- one least-privilege provisioner identity per execution cluster
- a separate Argo CD destination identity
- immutable image, model, ingress, and capability registration
- API readiness and cluster eligibility validation
- Launchpad-driven group reclaim and zero-residue proof

**Every `oc` invocation uses an explicit kubeconfig.**

<!--
Point to deploy/ecosystem. It is a thin orchestrator around repository-native
contracts, not a new AgnosticD implementation and not a kubeadmin workflow.
-->

---

<!-- _class: compact -->

# Next gates

1. Complete requester, participant, lab, and admin visual acceptance
2. Establish stable public DNS, TLS, ingress, and SSO ownership
3. Route participant inference through version-pinned LiteLLM and prove attribution
4. Deploy and manually validate the Keycloak 26.7.2 candidate
5. Exercise lifecycle HA and Flightpath promotion/failback
6. Spike the GCL/GeoLux decision-provider contract
7. Onboard the next quickstart through the new repository pipeline

<!--
These are deliberate release gates, not hidden defects. The internal 3x25
automated pilot proof remains valid while these paths graduate independently.
-->

---

<!-- _class: lead -->

# One entry point.

### Distributed workshops. Governed operations. Verifiable cleanup.

<div class="logos">
  <img src="../../demos/frontend/public/intel-logo.svg" alt="Intel">
  <span class="redhat-lockup"><img src="../../frontend/public/logos/redhat.svg" alt="">Red Hat</span>
</div>

<span class="muted">github.com/rhpds/launchpad</span>

<!--
Close on the operating model: reusable content plus lifecycle proof. Offer the
live demo or architecture deep dive depending on the audience.
-->
