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

1. Declare the business workload, success criteria, human-authority boundary,
   and provisional operating envelope.
2. Confirm the certified 401 baseline, then trace one complete request through
   orchestrator, agents, MCP, policy, Intel Xeon inference, and human review.
3. Run the immutable evaluation set at the baseline profile and record quality,
   policy agreement, latency, tokens, queues, and evidence provenance.
4. Increase one workload dimension at a time: agent replicas, journey
   concurrency, and inference pressure. Apply the sustained and pressure
   profiles only after the preceding checkpoint is understood.
5. Compare performance, supported-decision quality, policy consistency, and
   review-required state against the same baseline cases.
6. Under declared sustained load, exercise dependency degradation,
   backpressure, retry limits, safe failure, and recovery one boundary at a
   time.
7. Identify the first measured constraint, distinguish request-attributed
   inference evidence from shared endpoint CPU evidence, and define the
   supported workload operating envelope.
8. Generate the signed workload report and restore the single-replica baseline.

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

The learner-facing gates are defined by
`contracts/agentic-workload-scale-v1.yaml`. Its initial thresholds are
explicitly provisional until a reviewed one-seat baseline approves or revises
them. Any threshold revision requires versioned rationale and approval; results
cannot be reinterpreted after a run to manufacture a pass.

Launchpad delivery is governed separately by
`contracts/catalog-scale-delivery-certification-v1.yaml` and
`certification/catalog/scale-agentic-blueprint.yaml`. Learner workload execution
has its own fail-closed charter at
`certification/workload/scale-agentic-blueprint.yaml`. It becomes executable
only after the 401 prerequisite, live load adapter, evaluation set, telemetry,
and fault boundaries are ready.

The initial workload measurement harness is `scripts/agentic_scale_harness.py`. It can
produce deterministic, hashed baseline, sustained, and pressure plans from the
balanced 30-case set in `evaluation/agentic-scale-v1.yaml`. Live execution is
fail-closed while the certification charter is disabled; the planner does not
make network calls or manufacture results.

The learner scales one workload in one assigned namespace. Launchpad operators,
outside the learner journey, separately certify delivery to 1, 5, and 25
participant environments, including isolation, provisioning, reclaim, and zero
residue. Those seat-promotion runs are release evidence, not lab exercises.

## Future specialty episodes

- Agentic performance engineering
- Agentic resilience and recovery
- Heterogeneous inference at scale
- Agentic governance at scale
- Multi-cluster agentic operations, only after the platform supports it
