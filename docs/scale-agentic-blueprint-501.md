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

## Future specialty episodes

- Agentic performance engineering
- Agentic resilience and recovery
- Heterogeneous inference at scale
- Agentic governance at scale
- Multi-cluster agentic operations, only after the platform supports it
