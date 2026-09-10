# Ecosystem enablement proof matrix

## Decision

The presentation, architecture/scale roadmap, support model, portable
orchestration playbooks, and quickstart-repository onboarding first mile are
**GREEN-local**. They are ready for repository review and a controlled dry run.
They are not GREEN-live: no new control-plane deployment or execution-cluster
registration was authorized by this documentation iteration.

## Development evidence

| Method | Evidence | Result |
|---|---|---|
| TDD | Quickstart discovery tests were added first and failed on the missing `discover_quickstart_repo` contract | RED retained in task transcript; GREEN in the current suite |
| EDD | Current-state claims point to the September 17 status/evidence; deck source, rendered slides, tests, and checks are versioned | GREEN-local |
| CDD | `scaffold` takes immutable repo URL/SHA and identity inputs; returns intake YAML plus a JSON discovery receipt | GREEN-local |
| BDD | Valid quickstart → fail-closed draft; missing content/workload → nonzero failure; owner uses one deploy/validate/reclaim path | GREEN-local for onboarding; playbook dry run pending |
| CBT | Repository discovery, CLI, docs, playbook YAML, deck assets, PPTX archive, and PDF/PNG rendering were checked independently | GREEN-local |

## Red/green matrix

| Requirement | RED condition | GREEN-local proof | GREEN-live gate |
|---|---|---|---|
| Current architecture | Stale single-cluster or fail-open description | Arena/Brutus/Oberon/Flightpath boundaries documented | Operator confirms against deployed registry |
| Scale roadmap | “75 seats” lacks topology and limits | 3 x 25 staggered/order-affine proof and 50/75 gates stated | Next exact rehearsal and measured percentiles |
| Demo walkthrough | No reusable presenter sequence | 20-minute run-of-show, proof statements, and fallbacks | Manual browser rehearsal |
| DeepField/StarGate integration | Components shown as lifecycle authorities | Signal/classification/decision/execution boundaries defined | Versioned adapter contract and fault injection |
| GCL/GeoLux decision | An arbitrary product is selected | Common provider contract and selection spike defined | Reviewed decision record and approved implementation |
| Support | Direct namespace deletion is the recovery path | Severity, correlation, bounded actions, group reclaim, escalation | Event support rehearsal |
| Portable deployment | Implicit global context or shared admin credentials | Explicit kubeconfigs, dedicated identities, fail-closed asserts | Ansible syntax check and non-production dry run |
| Reclaim | Cleanup may target a fallback cluster | Persisted target assertion and zero-residue checks | Controlled workshop reclaim run |
| Quickstart onboarding | Every repo needs manual platform edits | Discovery/scaffold → existing render/validate/certify path | Onboard the next real quickstart revision |
| Presentation | No reusable deck | Git-editable Marp source plus a 15-slide PowerPoint deck rebuilt from the approved GCL/EvalHub reference template, with speaker notes, native tables, and full-slide visual validation | Stakeholder delivery rehearsal |

## Release rubric

| Category | Weight | Current | Remaining proof |
|---|---:|---:|---|
| Architecture truth and release boundaries | 15 | 15 | Live operator confirmation |
| Presentation and demo flow | 15 | 15 | Manual delivery rehearsal |
| Scale and integration roadmap | 15 | 15 | GCL/GeoLux decision spike |
| Support and reclamation safety | 15 | 15 | Event support drill |
| Quickstart onboarding contract | 20 | 20 | Next real repository adoption |
| Portable playbook safety | 15 | 10 | Ansible syntax plus controlled dry run |
| Evidence integrity and repository safety | 5 | 5 | CI retention after push |
| **Total** | **100** | **95 GREEN-local** | **Five points intentionally withheld until playbook dry run** |

Promotion to GREEN-live requires all 100 points. A successful documentation
review alone must not enable a cluster, promote a catalog, or authorize
automatic remediation.
