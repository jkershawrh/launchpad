# Agentic journey telemetry

The machine-readable authority is
[`../contracts/agentic-journey-telemetry-v1.yaml`](../contracts/agentic-journey-telemetry-v1.yaml).

Every core lab and specialty should expose the same correlated proof record.
The record connects what the learner sees to what the architecture actually
did.

## Required proof chain

1. Original request and scenario contract.
2. Orchestrator delegation and agent exchanges.
3. MCP tool requests and evidence provenance.
4. Evidence-ledger completeness.
5. Deterministic policy identifier, version, result, and reason codes.
6. Bounded prompt-in and response-out.
7. Intel model, endpoint, latency, tokens, and CPU allocation when available.
8. Human disposition and authorized action.
9. Failure, safe state, recovery, and deployment revision when applicable.

All records share journey, investigation, request, event, time, and component
identifiers. Trace and span identifiers are optional until the OpenTelemetry
runtime integration is certified.

Fallback data must be labelled `REHEARSAL`, `OFFLINE`, or `UNAVAILABLE`; only
a response collected from the configured runtime may be labelled `LIVE`.

