# Intel × Red Hat OpenShift AI — golden paths (CPU + Gaudi)

**Purpose:** Two **supported demo paths** for the Intel-sponsored OpenShift AI cluster at Rackspace: **Xeon6 CPU inference** and **Gaudi-accelerated inference**. After cluster discovery, replace every `[TBD]` with pinned versions (cluster version, operator catalog, image **digests**).

---

## Version pin sheet (fill from live cluster)

Record once per release train and update when the platform team bumps versions.

| Component | CPU path (Xeon6) | Gaudi path | Source of truth |
|-----------|------------------|------------|-------------------|
| OpenShift (`oc get clusterversion`) | `[TBD]` | `[TBD]` | Cluster |
| OpenShift AI / RHOAI operator | `[TBD]` | `[TBD]` | Installed Operators |
| Serving layer (e.g. KServe, Serverless if used) | `[TBD]` | `[TBD]` | OperatorHub / GitOps repo |
| Inference runtime (e.g. vLLM build) | `[TBD]` | `[TBD]` | ImageStream or deploy manifest |
| Habana / Gaudi stack (driver, plugin, user-space) | N/A | `[TBD]` | Node labels + Intel matrix |
| **Model artifact** (name, license, HF revision) | `[TBD]` | `[TBD]` | Internal model registry |
| **Image digest** (immutable pin) | `[TBD]` | `[TBD]` | `oc describe` / registry UI |

---

## Golden path A — LLM inference on **Xeon6 (CPU only)**

**Story for Intel / partners:** Cost-efficient inference and batch for **smaller** models or **latency-tolerant** workloads without consuming Gaudi capacity.

**Recommended stack (pick what matches your installed OpenShift AI):**

- **Serving:** `InferenceService` (KServe) or OpenShift AI model serving CRs already standardized on the cluster.  
- **Runtime:** **vLLM CPU** or the **CPU** profile of your approved serving runtime (must match operator docs for your RHOAI version).  
- **Scheduling:** Node selector / tolerations targeting **`[TBD: Xeon6 worker pool label]`**. **Do not** schedule on Gaudi nodes for this path.  
- **Model class:** Small instruct model appropriate for CPU (example families: **Phi-3-mini**, **TinyLlama**, **Llama-3.2-1B-Instruct** — **only** use weights your org has cleared for partner demos).

**Sizing defaults (tune after one benchmark run):**

- `[TBD]` CPU request/limit, memory request/limit, `max_model_len` / batch settings for vLLM.  
- Start conservative to avoid noisy-neighbor on shared workers.

**Success criteria for “green” quickstart:**

- Route returns HTTP 200; **time-to-first-token** and **tokens/s** logged in a standard dashboard.  
- Pod stays **Running** for 30 minutes under light load test script in runbook.

---

## Golden path B — LLM inference on **Intel Gaudi**

**Story for Intel / partners:** Accelerator-backed inference for **larger** models or **higher throughput** than the CPU path, using **Habana / Gaudi** integration supported on this cluster.

**Recommended stack:**

- **Serving:** Same **KServe / OpenShift AI** pattern as path A **unless** platform mandates a Gaudi-specific ServingRuntime (follow what is already validated on **this** cluster).  
- **Runtime:** **vLLM with Habana** or the **Habana-tuned** serving image your matrix lists — **must** match `[TBD: Habana user-space version]`.  
- **Scheduling:** Node selector for **`[TBD: Gaudi node label]`**; requests **`habana.ai/*`** resources as per device plugin.  
- **Model class:** One **medium** instruct model approved for GPU-class demos (e.g. **7B–8B** class — **only** if legal + capacity allow; otherwise smaller).

**Sizing defaults:**

- `[TBD]` Gaudi device fraction / HPU allocation per policy.  
- Document **max concurrent replicas** per partner namespace to protect others.

**Success criteria:**

- `oc describe node` / device metrics show **HPU utilization** under load.  
- Latency/throughput numbers captured for **Intel joint collateral** (even if internal-only at first).

---

## Teardown (required for every sandbox)

Run in order (adjust names):

1. **Delete inference workloads:** `InferenceService`, `ServingRuntime` instances, Knative Services (if any), Routes.  
2. **Delete workloads:** Deployments, StatefulSets, Jobs, CronJobs, PVCs (if partner data allowed — **wipe**).  
3. **Remove secrets:** pull secrets, HF tokens, TLS certs issued for that PoC.  
4. **Revoke access:** RoleBindings / Group memberships for partner users; remove from IdP group if used.  
5. **Optional:** Archive logs/metrics snapshot **only if** policy allows and retention is defined.  
6. **Delete project:** `oc delete project <partner-sandbox>` after confirmation from sponsor.

**Checklist owner:** `[TBD: Red Hat infra DRI]` signs off in ticket.

---

## TTL policy (suggested defaults — confirm with Rackspace capacity)

| Tier | Max lifetime | Extension | Auto-teardown |
|------|----------------|-----------|----------------|
| **Demo** | 14 calendar days | +7 days once, with sponsor approval | Yes — calendar reminder at day 10 |
| **PoC** | 30 calendar days | Requires joint Intel+RH re-approval | Yes — reminder at day 21 |

Automate reminders via ticket bot or GitOps “expires-after” annotation if your team adopts it.

---

## When to steer partners to CPU vs Gaudi

| Partner need | Start here |
|--------------|------------|
| Slide deck / “hello world” LLM | **CPU path** |
| Batch / offline scoring, cost-sensitive | **CPU path** |
| Higher throughput, larger context, interactive “wow” | **Gaudi path** (if model fits allow-list) |
| Training at scale | **Out of scope** unless explicitly enabled and resourced |

---

## Next actions for the AI SME / infra lead

1. Log in to the cluster; export `oc version` and operator versions into the **pin sheet**.  
2. Run one **smoke deploy** per path; save **exact** YAML + image digests to an internal Git repo.  
3. Attach this doc link to the **partner welcome pack** and the **stakeholder map** (`intel-rh-partner-platform-stakeholder-map.md`).

---

*Golden paths are templates until `[TBD]` fields are replaced with cluster-specific, tested values.*
