"""Agent Swarm — multi-agent coordination across Intel hardware."""

import random
import time
from dataclasses import dataclass
from typing import Dict, List, Any
from collections import Counter


@dataclass
class SwarmAgent:
    id: str
    name: str
    role: str
    hardware_lane: str
    task_type: str
    status: str = "pending"


# ─── Incident Investigation ───

INCIDENT_SWARM = {
    "name": "Incident Investigation Swarm",
    "description": "Specialized agents investigate a production incident in parallel across Intel Xeon 6 and Gaudi.",
    "agents": [
        {"id": "triage", "name": "Triage Agent", "role": "Classify severity and identify affected services", "hardware_lane": "xeon_eco", "task_type": "classification", "hw_label": "Intel Xeon 6 Eco", "model": "granite-4-0-h-tiny"},
        {"id": "log_analyst", "name": "Log Analyst", "role": "Parse logs and find error patterns", "hardware_lane": "xeon_performance", "task_type": "rerank", "hw_label": "Intel Xeon 6 + AMX", "model": "codellama-7b-instruct"},
        {"id": "metrics", "name": "Metrics Agent", "role": "Analyze dashboards and interpret charts", "hardware_lane": "gaudi_overdrive", "task_type": "chart_interpretation", "hw_label": "Intel Gaudi", "model": "llama-scout-17b"},
        {"id": "rca", "name": "RCA Agent", "role": "Deep root cause analysis combining all findings", "hardware_lane": "gaudi_overdrive", "task_type": "incident_rca", "hw_label": "Intel Gaudi", "model": "llama-scout-17b"},
        {"id": "reporter", "name": "Reporter Agent", "role": "Synthesize findings into executive report", "hardware_lane": "gaudi_overdrive", "task_type": "batch_summary", "hw_label": "Intel Gaudi", "model": "llama-scout-17b"},
        # Deep-level agents
        {"id": "security_analyst", "name": "Security Analyst", "role": "Check for security implications in the incident", "hardware_lane": "xeon_performance", "task_type": "rerank", "hw_label": "Intel Xeon 6 + AMX", "model": "codellama-7b-instruct"},
        {"id": "change_auditor", "name": "Change Auditor", "role": "Review recent deployments that may have caused the incident", "hardware_lane": "xeon_eco", "task_type": "classification", "hw_label": "Intel Xeon 6 Eco", "model": "granite-4-0-h-tiny"},
        {"id": "remediation_planner", "name": "Remediation Planner", "role": "Generate detailed fix plan with rollback steps", "hardware_lane": "gaudi_overdrive", "task_type": "long_summary", "hw_label": "Intel Gaudi", "model": "llama-scout-17b"},
    ],
    "waves": [
        {"wave": 1, "label": "Parallel Investigation", "agents": ["triage", "log_analyst", "metrics"], "depends_on": None, "desc": "Three agents investigate simultaneously — classification on Xeon 6, log analysis on Xeon 6 + AMX, dashboard interpretation on Gaudi."},
        {"wave": 2, "label": "Root Cause Analysis", "agents": ["rca"], "depends_on": 0, "desc": "RCA agent receives all findings from Wave 1 and performs deep analysis on Gaudi."},
        {"wave": 3, "label": "Report Generation", "agents": ["reporter"], "depends_on": 1, "desc": "Reporter synthesizes everything into an executive summary on Gaudi."},
        {"wave": 4, "label": "Validation & Remediation", "agents": ["security_analyst", "change_auditor", "remediation_planner"], "depends_on": 2, "desc": "Security review, change audit, and remediation planning run in parallel across Xeon 6 and Gaudi."},
    ],
    "depth_config": {
        "triage": {"agents": ["triage", "log_analyst", "reporter"], "waves": [0, 2]},
        "full": {"agents": ["triage", "log_analyst", "metrics", "rca", "reporter"], "waves": [0, 1, 2]},
        "deep": {"agents": ["triage", "log_analyst", "metrics", "rca", "reporter", "security_analyst", "change_auditor", "remediation_planner"], "waves": [0, 1, 2, 3]},
    },
}

# ─── Security Audit ───

SECURITY_AUDIT_SWARM = {
    "name": "Security Audit Swarm",
    "description": "Agents scan for vulnerabilities, compliance gaps, and threat vectors across Intel hardware.",
    "agents": [
        {"id": "vuln_scanner", "name": "Vulnerability Scanner", "role": "Scan for known CVEs and misconfigurations", "hardware_lane": "xeon_eco", "task_type": "classification", "hw_label": "Intel Xeon 6 Eco", "model": "granite-4-0-h-tiny"},
        {"id": "compliance", "name": "Compliance Checker", "role": "Verify against CIS benchmarks and SOC2 controls", "hardware_lane": "xeon_performance", "task_type": "rerank", "hw_label": "Intel Xeon 6 + AMX", "model": "codellama-7b-instruct"},
        {"id": "threat_analyst", "name": "Threat Analyst", "role": "Analyze threat vectors and attack surface", "hardware_lane": "gaudi_overdrive", "task_type": "incident_rca", "hw_label": "Intel Gaudi", "model": "llama-scout-17b"},
        {"id": "risk_assessor", "name": "Risk Assessor", "role": "Prioritize findings by business impact", "hardware_lane": "gaudi_overdrive", "task_type": "long_summary", "hw_label": "Intel Gaudi", "model": "llama-scout-17b"},
        {"id": "reporter", "name": "Audit Reporter", "role": "Generate executive security audit report", "hardware_lane": "gaudi_overdrive", "task_type": "batch_summary", "hw_label": "Intel Gaudi", "model": "llama-scout-17b"},
        # Deep-level agents
        {"id": "network_auditor", "name": "Network Auditor", "role": "Analyze network policies, ingress rules, and TLS configuration", "hardware_lane": "xeon_performance", "task_type": "rerank", "hw_label": "Intel Xeon 6 + AMX", "model": "codellama-7b-instruct"},
        {"id": "secrets_scanner", "name": "Secrets Scanner", "role": "Detect exposed secrets, tokens, and credentials in configs", "hardware_lane": "xeon_eco", "task_type": "classification", "hw_label": "Intel Xeon 6 Eco", "model": "granite-4-0-h-tiny"},
        {"id": "remediation_planner", "name": "Remediation Planner", "role": "Generate prioritized remediation roadmap with timelines", "hardware_lane": "gaudi_overdrive", "task_type": "long_summary", "hw_label": "Intel Gaudi", "model": "llama-scout-17b"},
    ],
    "waves": [
        {"wave": 1, "label": "Parallel Scanning", "agents": ["vuln_scanner", "compliance", "threat_analyst"], "depends_on": None, "desc": "Three agents scan simultaneously — CVE detection on Xeon 6, compliance checks on Xeon 6 + AMX, threat analysis on Gaudi."},
        {"wave": 2, "label": "Risk Assessment", "agents": ["risk_assessor"], "depends_on": 0, "desc": "Risk assessor prioritizes all findings from Wave 1 by business impact on Gaudi."},
        {"wave": 3, "label": "Audit Report", "agents": ["reporter"], "depends_on": 1, "desc": "Reporter generates the executive security audit report on Gaudi."},
        {"wave": 4, "label": "Deep Audit & Remediation", "agents": ["network_auditor", "secrets_scanner", "remediation_planner"], "depends_on": 2, "desc": "Network audit, secrets scanning, and remediation planning run in parallel."},
    ],
    "depth_config": {
        "triage": {"agents": ["vuln_scanner", "compliance", "reporter"], "waves": [0, 2]},
        "full": {"agents": ["vuln_scanner", "compliance", "threat_analyst", "risk_assessor", "reporter"], "waves": [0, 1, 2]},
        "deep": {"agents": ["vuln_scanner", "compliance", "threat_analyst", "risk_assessor", "reporter", "network_auditor", "secrets_scanner", "remediation_planner"], "waves": [0, 1, 2, 3]},
    },
}

# ─── Capacity Planning ───

CAPACITY_PLANNING_SWARM = {
    "name": "Capacity Planning Swarm",
    "description": "Agents analyze resource utilization, model growth, and optimize infrastructure costs.",
    "agents": [
        {"id": "resource_analyst", "name": "Resource Analyst", "role": "Analyze current CPU, GPU, memory utilization across nodes", "hardware_lane": "xeon_eco", "task_type": "classification", "hw_label": "Intel Xeon 6 Eco", "model": "granite-4-0-h-tiny"},
        {"id": "traffic_modeler", "name": "Traffic Modeler", "role": "Model request patterns, peak hours, and seasonal trends", "hardware_lane": "xeon_performance", "task_type": "rerank", "hw_label": "Intel Xeon 6 + AMX", "model": "codellama-7b-instruct"},
        {"id": "growth_modeler", "name": "Growth Modeler", "role": "Project resource needs based on growth trajectory", "hardware_lane": "gaudi_overdrive", "task_type": "long_summary", "hw_label": "Intel Gaudi", "model": "llama-scout-17b"},
        {"id": "cost_optimizer", "name": "Cost Optimizer", "role": "Identify cost reduction opportunities across hardware tiers", "hardware_lane": "gaudi_overdrive", "task_type": "incident_rca", "hw_label": "Intel Gaudi", "model": "llama-scout-17b"},
        {"id": "reporter", "name": "Capacity Reporter", "role": "Generate executive capacity planning report", "hardware_lane": "gaudi_overdrive", "task_type": "batch_summary", "hw_label": "Intel Gaudi", "model": "llama-scout-17b"},
        # Deep-level agents
        {"id": "bin_packer", "name": "Bin Packing Optimizer", "role": "Optimize workload placement across Xeon 6 and Gaudi nodes", "hardware_lane": "xeon_performance", "task_type": "rerank", "hw_label": "Intel Xeon 6 + AMX", "model": "codellama-7b-instruct"},
        {"id": "sla_auditor", "name": "SLA Auditor", "role": "Verify capacity meets SLA commitments under projected load", "hardware_lane": "xeon_eco", "task_type": "classification", "hw_label": "Intel Xeon 6 Eco", "model": "granite-4-0-h-tiny"},
        {"id": "procurement_planner", "name": "Procurement Planner", "role": "Generate hardware procurement timeline with ROI analysis", "hardware_lane": "gaudi_overdrive", "task_type": "long_summary", "hw_label": "Intel Gaudi", "model": "llama-scout-17b"},
    ],
    "waves": [
        {"wave": 1, "label": "Data Collection", "agents": ["resource_analyst", "traffic_modeler", "growth_modeler"], "depends_on": None, "desc": "Three agents collect data simultaneously — utilization on Xeon 6, traffic patterns on Xeon 6 + AMX, growth modeling on Gaudi."},
        {"wave": 2, "label": "Cost Optimization", "agents": ["cost_optimizer"], "depends_on": 0, "desc": "Cost optimizer analyzes all data from Wave 1 and identifies savings opportunities."},
        {"wave": 3, "label": "Capacity Report", "agents": ["reporter"], "depends_on": 1, "desc": "Reporter generates the executive capacity planning report on Gaudi."},
        {"wave": 4, "label": "Deep Planning", "agents": ["bin_packer", "sla_auditor", "procurement_planner"], "depends_on": 2, "desc": "Bin packing optimization, SLA verification, and procurement planning run in parallel."},
    ],
    "depth_config": {
        "triage": {"agents": ["resource_analyst", "traffic_modeler", "reporter"], "waves": [0, 2]},
        "full": {"agents": ["resource_analyst", "traffic_modeler", "growth_modeler", "cost_optimizer", "reporter"], "waves": [0, 1, 2]},
        "deep": {"agents": ["resource_analyst", "traffic_modeler", "growth_modeler", "cost_optimizer", "reporter", "bin_packer", "sla_auditor", "procurement_planner"], "waves": [0, 1, 2, 3]},
    },
}

# ─── Mock Agent Outputs ───

MOCK_AGENT_OUTPUTS = {
    # Incident
    "triage": {
        "output": "Severity: P1 — CRITICAL\nAffected services: checkout-service, payment-service, inference-gateway\nImpact: Customer-facing checkout flow degraded. Inference latency exceeding SLA.\nInitial classification: Cascading failure originating from payment-service connection pool exhaustion.",
        "latency_ms": 85,
    },
    "log_analyst": {
        "output": "Error patterns found (last 30 minutes):\n1. 47x 'connection pool exhausted' in payment-service (14:23-14:50 UTC)\n2. 23x 'timeout connecting to payment-service' in checkout-service\n3. 12x 'fallback routing activated' in inference-gateway\n4. 8x 'HBM allocation failed' in gaudi-inference namespace\n\nTimeline: payment-service connection pool hit limit at 14:23 → cascade started at 14:25 → Gaudi HBM pressure at 14:28 → full degradation at 14:32",
        "latency_ms": 320,
    },
    "metrics": {
        "output": "Dashboard analysis (3 panels examined):\n1. Latency panel: p99 spike from 200ms to 4,500ms starting 14:23 UTC. Not load-driven (request volume stable at 850 req/s).\n2. Error rate panel: 0.1% → 3.2% correlated with latency spike. HTTP 502 errors concentrated on /v1/route endpoint.\n3. Resource panel: Gaudi HBM utilization hit 97% at 14:28. Xeon 6 CPU stable at 55%. Correlation: latency spike began 5 minutes before Gaudi saturation.",
        "latency_ms": 1200,
    },
    "rca": {
        "output": "ROOT CAUSE ANALYSIS\n\nPrimary cause: Payment-service connection pool exhaustion (limit: 50 connections, peak demand: 120)\n\nCascade chain:\n1. Payment-service pool saturated → checkout-service timeouts\n2. Checkout retries amplified load → payment-service further degraded\n3. Inference gateway batch job consumed 94GB of 96GB Gaudi HBM\n4. New inference requests queued → routing engine activated Xeon 6 fallback\n5. Xeon 6 Performance lane received 4x normal traffic → p99 spike\n\nContributing factor: Unthrottled batch-job-7842 consumed Gaudi HBM without resource limits.\n\nRecommended fix:\n- Immediate: Increase payment-service pool to 200, terminate batch-job-7842\n- Short-term: Add circuit breaker to checkout→payment path, add Gaudi resource limits\n- Long-term: Implement token budget admission controller for Gaudi lane",
        "latency_ms": 2800,
    },
    "reporter": {
        "output": "EXECUTIVE INCIDENT REPORT\n\nIncident: Production checkout degradation\nDuration: 27 minutes (14:23-14:50 UTC)\nSeverity: P1\nImpact: 142 requests exceeded SLA. Zero requests dropped.\n\nWhat happened: A payment-service connection pool limit caused checkout timeouts. Simultaneously, an unthrottled batch job consumed all Gaudi accelerator memory. The routing engine correctly fell back to Xeon 6, but the combined load from both failures caused temporary latency spikes.\n\nWhat worked: Intelligent routing detected Gaudi failure and rerouted to Xeon 6 within 2 minutes. No requests were dropped. The platform degraded gracefully.\n\nWhat to fix: Connection pool limits, Gaudi resource quotas, and batch job admission controls.\n\nHardware insight: Intel Xeon 6 handled the fallback traffic at acceptable latency. Intel Gaudi recovered fully once the batch job was terminated. The dual-path architecture prevented a complete outage.",
        "latency_ms": 3200,
    },
    "security_analyst": {
        "output": "SECURITY IMPACT ASSESSMENT\n\nFindings from incident analysis:\n1. No data exfiltration detected — connection pool exhaustion was resource-based, not injection\n2. Gaudi HBM allocation failure exposed internal IP addresses in error logs (LOW severity)\n3. Retry storm from checkout-service bypassed rate limiter — requests routed via internal service mesh\n4. No unauthorized access attempts correlated with the incident window\n\nRecommendation: Sanitize internal IPs from error responses. Add circuit-level rate limiting to prevent retry amplification.",
        "latency_ms": 450,
    },
    "change_auditor": {
        "output": "RECENT CHANGE AUDIT\n\nChanges in 48h window before incident:\n1. [14:00 UTC] batch-job-7842 deployed with no HBM resource limits (PR #1847 — missing resource spec)\n2. [12:30 UTC] payment-service scaled from 3→2 replicas (cost optimization — reduced pool from 75→50 connections)\n3. [09:00 UTC] inference-gateway config update — no functional change\n\nRoot cause correlation: Change #2 reduced connection pool capacity. Change #1 consumed Gaudi HBM. Together they created the cascading failure.",
        "latency_ms": 180,
    },
    "remediation_planner": {
        "output": "REMEDIATION PLAN\n\nImmediate (next 2 hours):\n1. Scale payment-service back to 3 replicas (restores pool to 75 connections)\n2. Terminate batch-job-7842 and add resource limits before re-deploy\n3. Verify Gaudi HBM recovered to <60% utilization\n\nShort-term (this sprint):\n1. Add circuit breaker to checkout→payment path (Istio retry budget: 3 retries, 5s timeout)\n2. Add Gaudi HBM resource quotas per namespace (max 80GB per job)\n3. Update deployment pipeline to require resource specs for GPU workloads\n\nRollback plan: If payment-service scale-up causes memory pressure, reduce to 2 replicas and increase pool-per-replica to 75.\n\nValidation: Run incident_storm workload simulation at Drive mode to verify fix holds under load.",
        "latency_ms": 2600,
    },
    # Security Audit
    "vuln_scanner": {
        "output": "VULNERABILITY SCAN RESULTS\n\nCritical (2):\n1. CVE-2024-21626 — container runtime escape in runc 1.1.11 (inference-gateway namespace)\n2. CVE-2024-3094 — xz-utils backdoor detected in base image python:3.11-slim\n\nHigh (5):\n3. Outdated TLS 1.2 configuration on internal API endpoints\n4. Default ServiceAccount has cluster-admin RBAC binding in staging namespace\n5. Gaudi device plugin running with privileged security context\n6. Missing network policy for inter-namespace traffic\n7. Prometheus metrics endpoint exposed without authentication\n\n14 Medium, 23 Low findings omitted for brevity.",
        "latency_ms": 95,
    },
    "compliance": {
        "output": "COMPLIANCE CHECK — CIS Kubernetes Benchmark v1.8\n\nPassed: 73/89 controls (82%)\nFailed: 16 controls\n\nCritical failures:\n1. [1.2.16] API server audit logging disabled\n2. [4.2.6] Protect kernel defaults not set on kubelet\n3. [5.1.6] ServiceAccounts not restricted to namespaces\n\nSOC2 gaps:\n1. No encryption at rest for etcd secrets (CC6.1)\n2. Audit trail incomplete — 4 namespaces missing log forwarding (CC7.2)\n3. No automated compliance drift detection (CC8.1)\n\nOverall: PARTIAL compliance. 3 critical controls must be remediated before audit.",
        "latency_ms": 380,
    },
    "threat_analyst": {
        "output": "THREAT ANALYSIS\n\nAttack surface assessment:\n1. External: 3 ingress controllers expose 12 routes. 2 routes lack WAF protection.\n2. Internal: Service mesh covers 85% of traffic. 15% bypasses Istio (legacy services).\n3. Supply chain: 4 container images pull from public registries without signature verification.\n4. Model serving: Inference endpoints accept arbitrary prompts — prompt injection risk on /v1/route.\n\nThreat vectors:\n- Container escape via CVE-2024-21626 → lateral movement to Gaudi nodes\n- Prompt injection → model exfiltration or unauthorized inference on Gaudi\n- Unsecured Prometheus → cluster topology reconnaissance\n\nRisk: HIGH. Container runtime CVE combined with privileged Gaudi plugin creates escalation path.",
        "latency_ms": 1400,
    },
    "risk_assessor": {
        "output": "RISK PRIORITIZATION\n\nRank | Finding | Impact | Likelihood | Risk Score\n1    | Container runtime CVE | Critical | High | 9.2\n2    | xz-utils backdoor | Critical | Medium | 8.5\n3    | Privileged Gaudi plugin | High | High | 8.0\n4    | Missing audit logging | High | Certain | 7.8\n5    | TLS 1.2 deprecation | Medium | High | 6.5\n\nBusiness impact:\n- Items 1-2: Potential cluster compromise. Remediation SLA: 24 hours.\n- Items 3-4: Compliance audit failure. Remediation SLA: 1 sprint.\n- Item 5: Regulatory risk. Remediation SLA: 30 days.\n\nEstimated remediation effort: 42 engineering hours across security and platform teams.",
        "latency_ms": 2400,
    },
    "network_auditor": {
        "output": "NETWORK AUDIT\n\nIngress analysis:\n- 3 ingress controllers (nginx, istio, haproxy). Only istio enforces mTLS.\n- 2 routes expose internal APIs without rate limiting.\n\nNetwork policies:\n- 4/12 namespaces have deny-all default policies\n- 8 namespaces allow unrestricted inter-namespace traffic\n- Gaudi inference namespace has no egress restrictions\n\nTLS configuration:\n- Internal: TLS 1.2 minimum (should be 1.3)\n- External: TLS 1.3 enforced on all ingress\n- 3 internal services use self-signed certificates expiring in <30 days\n\nRecommendation: Deploy deny-all default policies in all namespaces. Upgrade internal TLS minimum to 1.3.",
        "latency_ms": 350,
    },
    "secrets_scanner": {
        "output": "SECRETS SCAN\n\nExposed secrets detected:\n1. API key in ConfigMap (inference-gateway/config) — should be Secret\n2. Database connection string in environment variable (plaintext in pod spec)\n3. OAuth client secret committed in Git history (revoked but still visible)\n4. Default admin password in Grafana deployment (unchanged from initial setup)\n\nSecret management:\n- 67% of secrets use Kubernetes Secrets (not encrypted at rest)\n- 0% use external secret management (Vault, AWS SM)\n- No secret rotation policy in place\n\nRecommendation: Migrate to HashiCorp Vault for external secret management. Enable etcd encryption at rest. Rotate all detected credentials immediately.",
        "latency_ms": 120,
    },
    # Capacity Planning
    "resource_analyst": {
        "output": "RESOURCE UTILIZATION ANALYSIS\n\nCurrent cluster state (24h average):\n- Xeon 6 Eco nodes (3x): CPU 42%, Memory 58%, Network 23%\n- Xeon 6 Performance nodes (2x): CPU 67%, Memory 71%, AMX utilization 34%\n- Gaudi nodes (2x): HBM 53%, Compute 48%, PCIe bandwidth 31%\n\nPeak utilization (last 7 days):\n- Xeon 6: 89% CPU (Tuesday 14:00-16:00 UTC during incident storm)\n- Gaudi: 97% HBM (Wednesday batch processing window)\n\nBottleneck: Gaudi HBM is the limiting resource. Single large job can consume 94GB of 96GB available.",
        "latency_ms": 110,
    },
    "traffic_modeler": {
        "output": "TRAFFIC PATTERN ANALYSIS\n\nRequest volume (7-day average): 12,400 requests/hour\nPeak: 28,500 req/hr (Tuesday 14:00 UTC)\nTrough: 3,200 req/hr (Sunday 04:00 UTC)\n\nTask distribution:\n- Classification (Xeon Eco): 34% of volume, 8% of compute time\n- Embedding/Rerank (Xeon Perf): 28% of volume, 22% of compute time\n- Generation (Gaudi): 38% of volume, 70% of compute time\n\nTrend: Generation requests growing 15% month-over-month. Classification stable.\nPrediction: Gaudi saturation at current growth rate in ~6 weeks.",
        "latency_ms": 290,
    },
    "growth_modeler": {
        "output": "GROWTH PROJECTION (12-month)\n\nScenario modeling:\n1. Conservative (10% MoM): Gaudi capacity exceeded by month 3. Need 1 additional Gaudi node.\n2. Moderate (15% MoM): Gaudi capacity exceeded by month 2. Need 2 additional Gaudi + 1 Xeon 6.\n3. Aggressive (25% MoM): Gaudi capacity exceeded by month 1. Need 3 Gaudi + 2 Xeon 6.\n\nRecommendation: Plan for moderate growth. Procure 2 Gaudi accelerators (lead time: 8 weeks) and 1 Xeon 6 Performance node.\n\nCapacity headroom target: 30% across all hardware tiers to handle incident spikes without fallback degradation.",
        "latency_ms": 1500,
    },
    "cost_optimizer": {
        "output": "COST OPTIMIZATION ANALYSIS\n\nCurrent monthly cost: $47,200\n- Xeon 6 Eco: $4,800 (10%)\n- Xeon 6 Performance: $12,400 (26%)\n- Gaudi: $30,000 (64%)\n\nOptimization opportunities:\n1. Route 12% more classification tasks to Xeon Eco (save $1,800/mo)\n2. Schedule batch jobs during off-peak (reduce Gaudi peak by 15%, save $2,100/mo)\n3. Enable Gaudi memory sharing for small inference jobs (improve utilization 20%)\n4. Right-size Xeon Eco from 3→2 nodes during weekends (save $600/mo)\n\nProjected savings: $4,500/month (9.5%) with no performance impact.\nROI on routing optimization: 3 engineering days → $54,000/year savings.",
        "latency_ms": 2200,
    },
    "bin_packer": {
        "output": "BIN PACKING OPTIMIZATION\n\nCurrent placement efficiency: 67%\nOptimized placement efficiency: 84%\n\nRecommendations:\n1. Co-locate embedding + classification workloads on same Xeon 6 Eco nodes (compatible resource profiles)\n2. Separate batch generation from interactive inference on Gaudi (HBM contention)\n3. Pin latency-sensitive classification to dedicated Xeon 6 cores (P99 improvement: 35%)\n4. Use Gaudi memory tiering: small models in HBM tier 1, large models in tier 2\n\nExpected improvement: 17% better utilization with 12% lower P95 latency.",
        "latency_ms": 420,
    },
    "sla_auditor": {
        "output": "SLA COMPLIANCE AUDIT\n\nCurrent SLA: P95 latency <500ms for classification, <2000ms for generation\n\nCompliance (last 30 days):\n- Classification: 99.4% compliant (target: 99.9%) — 6 breaches during incident\n- Generation: 98.7% compliant (target: 99.5%) — 14 breaches during peak\n- Availability: 99.95% (target: 99.9%) — PASSING\n\nProjected under moderate growth:\n- Classification: Will breach SLA at 120% current load without additional Xeon 6\n- Generation: Will breach SLA at 110% current load without additional Gaudi\n\nRecommendation: Provision additional capacity before growth hits 110% threshold (estimated 6-8 weeks).",
        "latency_ms": 200,
    },
    "procurement_planner": {
        "output": "PROCUREMENT TIMELINE & ROI\n\nRecommended procurement (moderate growth scenario):\n\nPhase 1 (Month 1-2):\n- 2x Intel Gaudi 2 accelerator cards: $38,000\n- Installation + integration: 5 engineering days\n- ROI breakeven: Month 4 (avoids $12K/mo in SLA penalties)\n\nPhase 2 (Month 3-4):\n- 1x Intel Xeon 6 Performance node: $8,500\n- Rack space + networking: $1,200\n- ROI breakeven: Month 6\n\nTotal investment: $47,700\nProjected 12-month savings: $168,000 (SLA penalties avoided + optimization gains)\nNet ROI: 252%\n\nAlternative: Scale existing nodes with Intel AMX optimization — saves $15K in hardware but requires 10 engineering days.",
        "latency_ms": 2800,
    },
}

SWARM_SCENARIOS = {
    "incident": INCIDENT_SWARM,
    "security_audit": SECURITY_AUDIT_SWARM,
    "capacity_planning": CAPACITY_PLANNING_SWARM,
}

SCENARIO_NARRATIVES = {
    "incident": {
        "title": "Incident Investigation",
        "story": "A P1 production incident has been triggered: checkout service degradation with Gaudi memory pressure. The swarm dispatches specialized agents to investigate, analyze, and report — fast tasks on Xeon 6, heavy reasoning on Gaudi.",
    },
    "security_audit": {
        "title": "Security Audit",
        "story": "A comprehensive security audit of the AI inference platform. Agents scan for vulnerabilities, verify compliance, analyze threats, and generate a prioritized remediation plan — all running across Intel hardware tiers.",
    },
    "capacity_planning": {
        "title": "Capacity Planning",
        "story": "The platform is growing. Agents analyze current utilization, model traffic patterns, project growth, optimize costs, and generate a procurement plan — ensuring Intel hardware scales with demand.",
    },
}

DELAY_SCALE = 0.7
DELAY_MIN = 0.3
DELAY_MAX = 2.5


def _get_depth_config(swarm: dict, depth: str) -> tuple:
    dc = swarm["depth_config"][depth]
    agent_ids = set(dc["agents"])
    wave_indices = dc["waves"]
    agents = [a for a in swarm["agents"] if a["id"] in agent_ids]
    waves = []
    for wi in wave_indices:
        w = dict(swarm["waves"][wi])
        w["agents"] = [a for a in w["agents"] if a in agent_ids]
        if w["agents"]:
            waves.append(w)
    return agents, waves


def run_swarm(scenario: str = "incident", depth: str = "full", seed: int = 42, run_state: dict = None) -> dict:
    swarm = SWARM_SCENARIOS.get(scenario, INCIDENT_SWARM)
    rng = random.Random(seed)

    agents_list, waves = _get_depth_config(swarm, depth)
    agents = {a["id"]: {**a, "status": "pending"} for a in agents_list}
    timeline = []
    agent_results = []
    start = time.monotonic()

    for wave_idx, wave in enumerate(waves):
        for agent_id in wave["agents"]:
            agent = agents[agent_id]
            agent["status"] = "running"

            if run_state:
                run_state["agent_results"] = list(agent_results)
                run_state["timeline"] = list(timeline)
                run_state["current_wave"] = wave_idx + 1

            t0 = time.monotonic() - start
            mock = MOCK_AGENT_OUTPUTS.get(agent_id, {"output": f"[{agent_id} analysis complete]", "latency_ms": 500})
            jitter = rng.uniform(0.8, 1.2)
            latency = round(mock["latency_ms"] * jitter, 1)

            delay = min(DELAY_MAX, max(DELAY_MIN, latency / 1000 * DELAY_SCALE))
            time.sleep(delay)

            agent["status"] = "done"
            t1 = time.monotonic() - start

            result = {
                "agent_id": agent_id,
                "name": agent["name"],
                "role": agent["role"],
                "hardware_lane": agent["hardware_lane"],
                "hw_label": agent.get("hw_label", agent["hardware_lane"]),
                "model": agent.get("model", "unknown"),
                "status": "done",
                "output": mock["output"],
                "latency_ms": latency,
                "wave": wave_idx + 1,
            }
            agent_results.append(result)

            timeline.append({
                "agent_id": agent_id,
                "name": agent["name"],
                "wave": wave_idx + 1,
                "hw": agent.get("hw_label", ""),
                "started_at": round(t0, 2),
                "completed_at": round(t1, 2),
                "latency_ms": latency,
            })

        if run_state:
            run_state["agent_results"] = list(agent_results)
            run_state["timeline"] = list(timeline)
            run_state["current_wave"] = wave_idx + 1

    total_ms = round((time.monotonic() - start) * 1000, 1)

    reporter_output = next((r["output"] for r in agent_results if r["agent_id"] == "reporter"), "")

    # Hardware utilization
    hw_counts = Counter(r["hardware_lane"] for r in agent_results)
    total_agents = len(agent_results)
    hw_utilization = {}
    for lane in ["xeon_eco", "xeon_performance", "gaudi_overdrive"]:
        hw_utilization[lane] = round(hw_counts.get(lane, 0) / total_agents * 100, 1)

    # Parallel speedup — sequential time vs wave-parallel time
    sequential_ms = sum(r["latency_ms"] for r in agent_results)
    wave_nums = sorted(set(r["wave"] for r in agent_results))
    wall_ms = sum(max((r["latency_ms"] for r in agent_results if r["wave"] == w), default=0) for w in wave_nums)
    parallel_speedup = round(sequential_ms / max(wall_ms, 0.1), 1)
    if parallel_speedup <= 1.0 and len(agent_results) > 1:
        parallel_speedup = round(len(agent_results) / len(wave_nums), 1)

    # Route counts for cockpit integration
    lane_map = {"xeon_eco": "eco", "xeon_performance": "performance", "gaudi_overdrive": "overdrive"}
    route_counts = {}
    for r in agent_results:
        lane = lane_map.get(r["hardware_lane"], "unknown")
        route_counts[lane] = route_counts.get(lane, 0) + 1

    result = {
        "status": "completed",
        "scenario": scenario,
        "depth": depth,
        "swarm_name": swarm["name"],
        "agent_count": len(agent_results),
        "wave_count": len(waves),
        "agent_results": agent_results,
        "timeline": timeline,
        "total_ms": total_ms,
        "final_report": reporter_output,
        "waves": waves,
        "hw_utilization": hw_utilization,
        "parallel_speedup": parallel_speedup,
        "route_counts": route_counts,
    }

    if run_state:
        run_state.update(result)

    return result
