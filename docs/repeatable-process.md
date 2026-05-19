# Repeatable Process

## Why Repeatability Matters

Every lab request follows the same lifecycle every time. No hand-built demo snowflakes. No undocumented manual setup. No hidden state. No "works on my cluster."

The platform enforces this by requiring every session to produce a complete set of artifacts before it is considered ready.

## Required Artifacts Per Lab

Every lab run must produce all six artifacts:

| # | Artifact | What it is |
|---|----------|------------|
| 1 | **Request record** | LabRequest with tenant, catalog item, mode, TTL, hardware/quota profile |
| 2 | **Provisioning plan** | Generated steps — namespace creation, quota, RBAC, deploy, gateway config |
| 3 | **Session record** | LabSession with namespace, URLs, status, lifecycle events |
| 4 | **Validation results** | List of ValidationResult (pass/fail/warn/skipped) with evidence |
| 5 | **Handoff package** | Lab URL, dashboard URL, MaaS key, access instructions, README, TTL |
| 6 | **Showback record** | Tenant, duration, CPU/memory/storage, Gaudi usage, token count, cost estimate |

## Lifecycle State Machine

Sessions follow a deterministic state machine with 15 valid transitions:

```
REQUESTED -> PROVISIONING
PROVISIONING -> VALIDATING
PROVISIONING -> FAILED
VALIDATING -> READY
VALIDATING -> VALIDATION_FAILED
READY -> ACTIVE
ACTIVE -> EXPIRED
ACTIVE -> RESETTING
EXPIRED -> RESETTING
EXPIRED -> RECLAIMED
RESETTING -> RECLAIMED
RESETTING -> CLEANUP_FAILED
FAILED -> RECLAIMED
VALIDATION_FAILED -> RECLAIMED
CLEANUP_FAILED -> RECLAIMED
```

Invalid transitions raise `InvalidTransitionError`. The transition to READY from VALIDATING requires all validation results to be present and none to have `result: fail`.

## Repeatability Score

The `RepeatabilityReport` produces a deterministic score out of 100:

| Check | Points |
|-------|--------|
| Catalog item versioned | +20 |
| Provisioning plan generated | +20 |
| Validation passed | +20 |
| Handoff generated | +20 |
| Showback generated | +10 |
| Cleanup defined | +10 |

A score of 100 means all artifacts were generated. Any score below 100 identifies exactly which part of the process was skipped or failed.

## No Hand-Built Snowflakes

- Every catalog item defines its inputs, capabilities, provisioning steps, validation checks, handoff outputs, observability profile, reset/reclaim steps, and showback metadata.
- Every session is reproducible from its request + catalog item + tenant.
- Request and plan hashes enable drift detection between runs.
