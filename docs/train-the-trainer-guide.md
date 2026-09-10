# Intel September 17 Demo Day train-the-trainer guide

## Purpose

This master guide prepares an instructor to demonstrate and facilitate the
three September 17 catalog experiences in this order:

1. **Intel AI Quickstart: Serve LLMs on Intel Xeon CPUs**
2. **Intel Xeon 6 201: Building an AI Agent**
3. **Build Multi-Agent AI Systems with Open Protocols**

Launchpad assigns isolated participant environments, renders the correct
Showroom journey, connects workloads to shared inference, validates the
participant-facing result, and reclaims the whole workshop through one managed
lifecycle.

This is a supervised pilot. Do not describe temporary Cloudflare Quick
Tunnels, public OpenShift Console access, or automated remediation as
production-ready.

## Trainer handoff

The event owner provides the participant URL and instructor code immediately
before the session. Do not store the code in Git, slides, recordings, or
support tickets. The styled HTML guide reads short-lived values from the
Git-ignored `train-the-trainer-live.js` file.

| Item | Session value |
|---|---|
| Participant URL | Supplied by the event owner |
| Instructor code | Supplied once by the event owner |
| Allowed email | Any email for an unclaimed seat; reuse it to resume |
| Duration | Four hours from order creation unless otherwise specified |
| Placement | Serve LLMs and Multi-Agent on Arena; Building an AI Agent on Brutus |
| Support | Launchpad operator |

## Recommended 90-minute trainer agenda

| Time | Topic | Outcome |
|---:|---|---|
| 0-10 min | Platform, access, and scope | Explain the shared lifecycle and participant boundary |
| 10-20 min | Showroom and namespace | Prove that Terminal is scoped to the assigned project |
| 20-38 min | Serve LLMs | Prove CPU inference and grounded RAG |
| 38-56 min | Building an AI Agent | Prove MCP tools, orchestration, and prompt tuning |
| 56-74 min | Build Multi-Agent AI Systems | Prove the three-track journey and a live policy change |
| 74-82 min | Operations | Explain placement, lifecycle, observability, and isolation |
| 82-87 min | Recovery | Practice one bounded troubleshooting path |
| 87-90 min | Reclaim | Explain cleanup ownership and retained proof |

Each full learner lab takes approximately 60-90 minutes. This agenda is a
trainer proof path, not a substitute for completing every Showroom module
during certification.

## Before participants arrive

Complete these checks 15 minutes before the session:

1. Connect to the Intel network or VPN for internal routes.
2. Confirm that all three intended workshop orders are `ready`, contain the
   expected number of seats, and have sufficient TTL remaining.
3. Open the participant URL in a fresh private window and confirm that the
   branded login page appears without consuming a seat.
4. Keep requester, operations, and participant sessions in separate browser
   profiles so their SSO cookies cannot mix.
5. For internal demonstrations, open the Arena and Brutus Console routes in
   top-level tabs and establish certificate trust before embedding them.
6. Keep one known-ready seat as a clearly identified fallback.

Internal operator links:

- Requester: <https://launchpad.apps.arena.fm2aihpcsed.com>
- Workshops: <https://launchpad.apps.arena.fm2aihpcsed.com/workshops>
- Operations: <https://launchpad-admin.apps.arena.fm2aihpcsed.com>
- System health: <https://launchpad-admin.apps.arena.fm2aihpcsed.com/system>
- Analytics: <https://launchpad-admin.apps.arena.fm2aihpcsed.com/analytics>

The internal portals use OpenShift authentication. The public participant flow
uses an email identity label plus the instructor code.

## Participant login and resume

1. Open the instructor-provided link in a fresh private window.
2. Enter an email and the instructor code exactly as supplied.
3. Select **Continue**. The first valid claim atomically assigns an open seat.
4. On **My Lab Access**, select the active environment and **Open Lab**.
5. To resume, reopen the same link with the same normalized email and code.

Email ownership is not verified in this pilot. The instructor code is the
secret; the email is an identity label.

## Common Showroom orientation

Every lab contains:

- **Instructions** for the guided exercise and expected result;
- **Terminal**, already authenticated and scoped to the seat namespace; and
- one catalog-specific application: **RAG Assistant**, **Solution Architect**,
  or **Multi-Agent Workspace**.

Public OpenShift Console SSO is not an external pilot gate. Use Terminal for
namespace proof:

```bash
oc whoami
oc project -q
oc get pods
oc auth can-i create deployments.apps
oc auth can-i get nodes
```

Expected: the project matches the assigned namespace, namespaced deployments
are allowed, and cluster node access is denied. Stop if the namespace is wrong.

## Lab 1: Intel AI Quickstart: Serve LLMs on Intel Xeon CPUs

### Outcome and architecture

Prove real shared CPU inference, build a namespace-isolated AnythingLLM
workspace, and compare a grounded RAG answer with a direct model response:

```text
Participant -> AnythingLLM -> OpenAI-compatible endpoint
            -> Granite model -> Intel Xeon CPU infrastructure
```

AnythingLLM is the RAG client, document pipeline, vector store, and UI. It
consumes the model; it does not host it.

### Verify model access

```bash
printf 'Model: %s\n' "$MAAS_MODEL"
curl -fsS "${MAAS_ENDPOINT}/v1/models" \
  -H "Authorization: Bearer ${MAAS_API_KEY}" | python3 -m json.tool

curl -fsS "${MAAS_ENDPOINT}/v1/chat/completions" \
  -H "Authorization: Bearer ${MAAS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"${MAAS_MODEL}\",
    \"messages\": [
      {\"role\": \"user\", \"content\": \"Explain RAG in two sentences.\"}
    ],
    \"max_tokens\": 100,
    \"temperature\": 0
  }" | python3 -m json.tool
```

The proof is a structurally valid response from the configured model, not just
a running pod.

### Build the RAG Assistant

1. Open **RAG Assistant** and return to its home screen if Admin is visible.
2. Create an **HR Assistant workspace**, not an AnythingLLM agent.
3. Ask: `What is the role of an HR representative?`
4. In **Settings -> API Keys**, create an API key and keep it off-screen.

```bash
export ANYTHINGLLM_API_KEY="paste-the-generated-key"
export ANYTHINGLLM_API_URL="http://anythingllm:3001"
curl -fsS "${ANYTHINGLLM_API_URL}/api/ping" | python3 -m json.tool

curl -fsS -X POST "${ANYTHINGLLM_API_URL}/api/v1/workspace/new" \
  -H "Authorization: Bearer ${ANYTHINGLLM_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"name":"hr-assistant"}' | python3 -m json.tool
```

Use the namespace-local Service for Terminal commands; do not substitute the
browser Route. Complete **Load and Chunk Documents**, embed the FMLA source,
and ask:

```text
What are the eligibility requirements for FMLA leave?
```

Ask the same question directly through MaaS. The grounded answer should contain
specific retrieved requirements and source evidence. `No MCP servers found` is
expected if the user entered Agent Skills; return home and use a workspace.

### Lab 1 evidence

- configured model responds successfully;
- AnythingLLM health endpoint responds;
- the HR Assistant workspace contains the FMLA document; and
- grounded and direct answers visibly differ in source use.

## Lab 2: Intel Xeon 6 201: Building an AI Agent

### Outcome

Build an auditable solution-advisor agent with a system prompt, LangGraph
workflow, three MCP tools, and a participant-visible UI.

### Establish the baseline

The initial namespace contains Showroom only. Follow the immutable manifest
links rendered in Showroom.

```bash
oc project -q
oc get pods
```

### Deploy and inspect MCP tools

```bash
oc rollout status deployment/solution-agent --timeout=90s
oc get pods -l app=solution-agent
export MCP_URL="http://solution-tools:8095"
curl -fsS -X POST "${MCP_URL}/mcp" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}' \
  | jq '.result.tools[] | {name, description}'
```

Expected tools cover Intel hardware, OpenShift capabilities, and reference
architectures. Call one and show its structured result before invoking the LLM.

### Wire the agent and generate a solution brief

```bash
oc rollout status deployment/solution-ui --timeout=90s
oc get pods -l app=solution-agent
oc get pods -l app=solution-ui
export ADVISOR_API_URL="http://solution-agent:8082"

curl -fsS -X POST "${ADVISOR_API_URL}/api/v1/advise" \
  -H "Content-Type: application/json" \
  -d '{
    "query":"A retail chain needs real-time inventory prediction across 500 stores with on-premises processing and a controlled infrastructure budget."
  }' | jq '.'
```

Open **Solution Architect** and repeat the query. Verify extracted requirements,
Intel hardware options, OpenShift capabilities, architecture, and tool/inference
logs.

In **Make It Yours**, inspect `advisor-prompt`, apply the instructed custom
prompt, restart `solution-agent`, and compare the result. Do not type an
arbitrary model name; the order controls the authorized model.

### Lab 2 evidence

- `solution-agent` and `solution-ui` are ready;
- three MCP tools are discoverable;
- a structured solution brief is returned;
- tool and inference logs are visible; and
- a prompt change produces an explainable behavior change.

## Lab 3: Build Multi-Agent AI Systems with Open Protocols

### Outcome and tracks

This is one lab with one namespace and three tracks:

1. **Run locally** explains the source and application pattern.
2. **Build and operate on OpenShift** is the live 25-seat-certified path.
3. **Advanced blueprint alignment** maps the live system to Kagenti,
   OpenTelemetry, workload identity, and governance.

Track 3 is architecture and manifest exploration; it does not prove that every
optional operator is installed in the participant namespace.

### Verify the deployed system

```bash
oc project -q
oc auth can-i get pods
oc auth can-i create deployments.apps
oc auth can-i get pods -n partner-ai-launchpad
oc auth can-i get nodes
oc get deployments,pods,services,routes
oc rollout status deployment/multi-agent --timeout=5m
```

The participant must be able to work only in the assigned namespace.

### Compare routing depth

In **Multi-Agent Workspace**, select `auto` and run:

```text
Create a short task to verify a fictional service health endpoint.
```

Then run:

```text
Research a fictional API latency increase, analyze likely causes, and create a remediation task.
```

The first request should take the shorter route. The second should involve the
research, analyst, and executor roles. Capture routing decision, agents, steps,
MCP data, and workflow errors.

### Apply and restore an executor policy

```bash
oc create configmap workflow-policy \
  --from-literal=AGENT_MAX_TOKENS_OVERRIDE=48 \
  --dry-run=client -o yaml | oc apply -f -

oc rollout restart deployment/multi-agent
oc rollout status deployment/multi-agent --timeout=5m
oc exec deployment/multi-agent -c executor -- \
  python -c 'import agent; print(agent.AGENT_MAX_TOKENS)'
```

The final command must print `48`. Repeat the comprehensive workflow, then
restore the certified baseline:

```bash
oc delete configmap workflow-policy
oc rollout restart deployment/multi-agent
oc rollout status deployment/multi-agent --timeout=5m
test "$(oc get configmap workflow-policy --ignore-not-found)" = ""
test "$(oc exec deployment/multi-agent -c executor -- \
  python -c 'import agent; print(agent.AGENT_MAX_TOKENS)')" = "96"
```

### Lab 3 evidence

- successful short and comprehensive workflows;
- token bound changes to `48`;
- token bound returns to `96`; and
- the temporary ConfigMap is absent.

## Platform story

| Catalog | Learning outcome | Pilot placement |
|---|---|---|
| Intel AI Quickstart: Serve LLMs on Intel Xeon CPUs | CPU inference and isolated RAG | Arena |
| Intel Xeon 6 201: Building an AI Agent | LangGraph, MCP tools, prompt tuning, and a solution brief | Brutus |
| Build Multi-Agent AI Systems with Open Protocols | Local pattern, OpenShift operation, and advanced blueprint | Arena |

Show the catalog, preview a 25-seat workshop without submitting it, explain
whole-workshop placement, show grouped seat state and cluster health, and end
with group-scoped idempotent reclaim.

Use this scale statement:

> We staggered three 25-seat orders, then ran all 75 participant environments
> concurrently across Arena and Brutus.

Do not claim simultaneous provisioning of all 75 seats or arbitrary catalog
portability.

## Troubleshooting

| Symptom | Trainer action |
|---|---|
| Code rejected | Confirm the link/code pair, remove spaces, and reuse the same email for resume |
| Different user already authenticated | Sign out, close the private window, and start a clean private session |
| Participant URL stops resolving | Escalate; the temporary tunnel process must remain running |
| Internal certificate error | Open the cluster route top-level, establish trust, and reload Showroom |
| Terminal reconnects | Wait 30 seconds and retry once, then verify the Showroom pod |
| Wrong namespace | Stop and escalate; never widen RBAC or switch projects manually |
| Model is warming | Use the bounded retry; do not silently substitute a model |
| AnythingLLM returns HTML | Use `http://anythingllm:3001` and retry `/api/ping` |
| MCP call returns 404 or TLS error | Use `http://solution-tools:8095/mcp` from Terminal |
| Solution Architect unavailable | Verify `solution-agent` and `solution-ui` rollouts |
| Multi-Agent workflow stalls | Check rollout/errors and restore the certified policy baseline |
| Public Console fails | Continue in Terminal; public Console SSO is not certified |

Before escalating, capture order ID, seat ID, cluster, namespace, timestamp,
error text, and browser request ID. Never include codes, API keys, kubeconfigs,
passwords, or OAuth callbacks.

## Reclaim and close

Do not delete pods, Routes, Applications, or namespaces manually.

1. End participant activity.
2. Reclaim the entire workshop through Launchpad.
3. Wait for all seats to reach a terminal reclaimed state.
4. Verify zero owned Namespaces, Routes, RoleBindings, Secrets, storage, model
   keys, or Argo CD Applications remain.
5. Save sanitized evidence and turn any failure into a regression test.

Close with these points:

- Git defines the catalog and learning journey.
- Launchpad owns placement, access, validation, visibility, and reclaim.
- Each seat is namespace-isolated and uses scoped credentials.
- Stable public ingress, trusted certificates, public Console SSO, and
  production HA/DR remain later gates.
