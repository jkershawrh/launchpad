# AI Operations Copilot Demo

**Intel + Red Hat can power governed AIOps from signal to action.**

## What This Shows Partners

An incident response pipeline where AI classification and correlation run on CPU, heavy reasoning runs on GPU, and a governance gate validates every action:

```
Alert: "Inference gateway p99 > 5s for 10 minutes"
    |
    v
[1] Classify severity ──> Xeon 6 / OpenVINO (<5ms)
    |
[2] Find similar incidents > Xeon 6 / OpenVINO (embed + search, <10ms)
    |     INC-2024-0891: API gateway latency spike
    |     INC-2025-0289: Model serving 503 errors
    |
[3] Generate RCA ────────> Gaudi / vLLM (7B model, <2s)
    |     "Connection pool exhaustion likely due to..."
    |
[4] Governance gate ─────> Policy engine (local, <1ms)
    |     Action: restart_service
    |     Risk: low → auto_approved
    v
Recommendation with full audit trail
```

The key: AI agents need more than inference. They need governed execution.

## Run

```bash
python3 app.py --alert "Pod OOM kills in gaudi-inference namespace, 3 restarts in 5 minutes"
python3 app.py --alert "SSL certificate expires in 24 hours on model serving route" --verbose
python3 app.py --json  # structured output
```

## Partner Message

> "AI operations copilots need fast classification (CPU), deep analysis (GPU),
> and policy-checked execution. Intel hardware handles both tiers.
> Red Hat provides the governance and platform."
