# Red Hat and Intel evidence-backed agentic blueprint

The machine-readable authority is
[`../contracts/agentic-blueprint-v1.yaml`](../contracts/agentic-blueprint-v1.yaml).

The blueprint is the common architecture beneath Launchpad's core agentic
journey and its specialty episodes. It is not a single user interface or one
industry scenario.

## Decision path

```text
Request or alarm
      |
      v
Orchestrator --A2A--> Specialized agents
      |                       |
      |                       v
      |                  Read-only MCP
      |                       |
      v                       v
Evidence ledger <------- Proven observations
      |
      v
Deterministic policy
      |
      +----> Unsupported or incomplete: abstain / request more evidence
      |
      v
Intel Xeon LLM adapter: bounded explanation
      |
      v
Human review: final disposition and action authority
```

Red Hat OpenShift supplies the deployment, isolation, operation, policy, and
progressive operator capabilities. Intel Xeon supplies the CPU inference
target. The LLM may explain a policy-supported conclusion; it does not own the
evidence, policy decision, or action.

## Specialty episodes

A specialty may introduce a domain, data source, tool, agent, policy, or
operator. It must declare where it branches from the core journey, what it
adds, the live proof it produces, and where the learner returns. It may not
remove evidence-first processing, deterministic policy, bounded LLM authority,
or human action authority.

## Runtime truth

The contract distinguishes live components from progressive capabilities and
architecture-only integrations. Kagenti and the OpenTelemetry runtime
integration remain architecture-only until separately deployed and certified.

