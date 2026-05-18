# Intel × Red Hat OpenShift AI partner platform — stakeholder map (one page)

**Purpose:** Clarify who does what for the Rackspace-hosted, Intel-sponsored OpenShift AI environment used for **joint partner demos, quickstarts, and PoCs**. Replace bracketed placeholders after kickoff with real names, channels, and ticket queues.

---

## Parties

| Party | Role on this program | Typical asks |
|--------|----------------------|--------------|
| **Partner** | Consumer of sandbox capacity for demo / PoC | Access, sample models, runbook steps, “does this hardware support our workload?” |
| **Red Hat (infra / AI SME)** | Platform patterns, OpenShift AI alignment, runbooks, quotas/TTLs, joint collateral inputs | Namespace design, serving stack defaults, escalation when product behavior unclear |
| **Intel** | Co-sponsor, hardware story (Gaudi, Xeon6), joint GTM with partners | Demo narratives, partner introductions, performance talking points, sometimes field SE support |
| **Rackspace** | Hosted fleet / underlying operations for this cluster | Infra incidents, node health, networking to cluster API, capacity at the **IaaS/hosting** layer |

---

## Support boundaries (default assumptions — confirm in writing)

| Layer | Owned / led by | Partner-visible? |
|--------|----------------|------------------|
| Physical hosts, rack power, hypervisor (if any), core network to cluster | **Rackspace** (confirm contract) | No — partner opens tickets via **RH/Intel agreed intake**, not directly to Rackspace unless contract says otherwise |
| OpenShift control plane health, etcd, upgrades (cluster scope) | **Rackspace** and/or **RH** per agreement — **fill in:** `[who runs upgrades?]` | Rarely — communicate via joint status page or bridge call |
| OpenShift **project/namespace**, quotas, NetworkPolicy, routes, TLS certs for apps | **Red Hat infra** (program team) with **Intel** alignment on messaging | Yes — via runbook + ticket |
| OpenShift AI operators, model serving CRs, notebook/image builds **inside** tenant | **Red Hat** (day-2 patterns) + **partner** self-service within policy | Yes — self-service within guardrails |
| Gaudi driver / device plugin / Habana stack versions | Split: **Rackspace** node image vs **RH/Intel** validated matrix — **fill in:** `[matrix owner]` | Partner sees **supported versions** only |
| Application bugs in partner’s own code or models | **Partner** | Yes — partner owns |

---

## Escalation (template)

1. **L1 — Partner / SE:** intake form or ticket → triage “access vs quota vs app bug.”  
2. **L2 — Red Hat program infra:** namespace, quotas, routes, image pulls, default quickstarts broken.  
3. **L3 — Rackspace / platform engineering:** node not ready, GPU device plugin cluster-wide failure, API outage.  
4. **L4 — Vendor (Intel / Habana / OEM):** firmware, Gaudi-specific defects **after** L3 confirms hardware/driver layer.

**Fill in after kickoff**

- Primary ticket queue / Jira / ServiceNow: `[link or ID]`  
- Pager or bridge for **Sev1** API down: `[contact]`  
- Slack / Teams channels: `[#channel-names]`  
- Business hours vs 24×7 for **partner-facing** issues: `[hours]`  

---

## Decision rights (avoid thrash)

| Decision | DRI (suggested) | Notes |
|----------|-----------------|--------|
| New partner admitted to sandbox | `[RH + Intel sponsor]` | Two-key rule reduces misuse |
| Model allow-list | `[RH legal/product + Intel]` | Keeps demos defensible |
| Default inference stack (CPU vs Gaudi path) | `[RH AI SME + Intel]` | Single story for collateral |
| Teardown / TTL policy | `[RH infra]` | Protects Rackspace capacity |

---

## Single paragraph you can paste to stakeholders

*The Rackspace environment hosts our Intel-sponsored OpenShift AI cluster (Gaudi and Xeon6 worker pools). Red Hat infra owns tenant onboarding, quotas, and golden-path runbooks inside OpenShift; Rackspace owns [confirm] host and cluster-level operations; Intel co-owns joint partner intake and hardware positioning. Partners consume sandboxes only through the agreed intake path; escalations flow from partner-facing tickets to Red Hat, then to Rackspace or vendors when the failure domain is clearly below the application layer.*

---

*Document version: draft for post-kickoff fill-in. Do not treat bracketed fields as factual until confirmed.*
