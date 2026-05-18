# Governed Agent Execution Demo

**AI agents need more than inference. They need governed execution.**

## What This Shows Partners

An agent wants to take an action. The platform classifies the intent, scores the risk, generates a plan, and makes a policy decision — all across the optimal hardware tier:

```
Request: "Restart inference pods to clear OOM state"
    |
    v
[1] Classify intent ────> Xeon 6 / OpenVINO (<5ms)
    |     Intent: restart_pod
    |
[2] Score risk ─────────> Xeon 6 / OpenVINO (<5ms)
    |     Risk: medium (0.50)
    |
[3] Generate plan ──────> Gaudi / vLLM (7B model, <2s)
    |     "1. Cordon node  2. Drain pods  3. Delete pods  4. Uncordon"
    |
[4] Policy validation ──> Local policy engine (<1ms)
    |     Decision: ALLOWED (audit required)
    v
Evidence bundle with full audit trail
```

Try dangerous requests to see the governance gates activate:

```bash
# This will be DENIED
python3 app.py --request "Delete the gaudi-inference namespace"

# This will be ESCALATED
python3 app.py --request "Patch the deployment to add privileged security context"

# This will be ALLOWED
python3 app.py --request "Read the logs from the inference gateway pods"
```

## Run

```bash
python3 app.py --request "Scale the CPU inference deployment to 5 replicas"
python3 app.py --request "Delete the production namespace" --verbose
python3 app.py --json  # structured output with evidence bundle
```

## Partner Message

> "AI agents that can take real actions need intent classification (CPU),
> risk scoring (CPU), execution planning (GPU), and policy validation —
> all with an auditable evidence trail. That's what this platform provides."
