# Intel AI 501: Scale and Certify Agentic Systems

## Purpose

The 501 experience extends the same Red Hat and Intel agentic blueprint used by
301 and operated in 401. It is a separate catalog item because scale testing has
different quotas, duration, observability, failure controls, and publication
gates. It is not a separate architecture.

## Learner outcome

The learner establishes a defensible operating envelope for an evidence-backed
multi-agent system. Completion means producing measured evidence for capacity,
quality, policy consistency, resilience, recovery, Intel Xeon inference, and
cleanup—not merely increasing a replica count.

## Proposed journey

1. Confirm the certified 401 baseline and declare the test envelope.
2. Scale agent replicas, concurrent journeys, and inference demand.
3. Route workloads by capability, latency objective, and available compute.
4. Apply versioned load profiles at one, five, and twenty-five seats.
5. Trace request, orchestrator, agent, MCP, policy, LLM, and human review.
6. Exercise dependency degradation, backpressure, retry limits, and recovery.
7. Compare answer quality and policy compliance against the baseline.
8. Measure throughput, p50/p95 latency, tokens, CPU allocation, and saturation.
9. Generate a signed certification evidence package and prove zero-residue reclaim.

## Architecture boundary

501 reuses the canonical `red-hat-intel-agentic-v1` contracts and the 401
runtime until evidence justifies a versioned change. The Intel story remains
measured Xeon inference inside the end-to-end journey. The Red Hat story remains
OpenShift deployment, scaling, observability, policy, recovery, and lifecycle
control.

## Truth boundary

This file is a charter, not a completed lab. The catalog item remains draft,
non-orderable, and content-only until the 401 prerequisite is certified and all
activation blockers have evidence. No projected metric may be presented as a
live result.

The executable gates are defined by
`contracts/agentic-scale-certification-v1.yaml`. Its initial thresholds are
explicitly provisional until a reviewed one-seat baseline approves or revises
them. Any threshold revision requires versioned rationale and approval; results
cannot be reinterpreted after a run to manufacture a pass.

`certification/catalog/scale-agentic-blueprint.yaml` is intentionally marked
`execution_enabled: false`. It becomes executable only after the 401
prerequisite, immutable artifacts, live load adapter, evaluation set, telemetry,
and fault boundaries are ready.

The initial measurement harness is `scripts/agentic_scale_harness.py`. It can
produce deterministic, hashed run plans for all three profiles from the
balanced 30-case set in `evaluation/agentic-scale-v1.yaml`. Live execution is
fail-closed while the certification charter is disabled; the planner does not
make network calls or manufacture results.

## Future specialty episodes

- Agentic performance engineering
- Agentic resilience and recovery
- Heterogeneous inference at scale
- Agentic governance at scale
- Multi-cluster agentic operations, only after the platform supports it
