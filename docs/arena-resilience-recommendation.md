# Arena workshop-load resilience recommendation

## Outcome

Arena completed all 75 catalog-specific participant functions, but it is not production-certified for network resilience. The controlled five-seat restart cohorts prevented functional loss; they did not remove correlated readiness and liveness timeouts across workshop and OpenShift namespaces.

The strongest current explanation is that the certifier itself is materially amplifying kubelet/CRI pressure. Twenty-five Multi-Agent validators used concurrent `oc exec` streams while the lab traffic ran, and kubelet `exec_sync` p99 reached 14.72 seconds on `gnr2` and 10.72 seconds on `rhgnr1`. Host CPU peaked at only 16.45% and 2.45%, and interface drop/error counters stayed at zero. This makes ordinary host CPU exhaustion or physical network loss poor single-cause explanations.

`rhgnr1` has an additional concrete risk: conntrack reached 87.8% of its 262,144-entry limit during the run. That can worsen connection setup and must be investigated even though it does not explain the initial `gnr2` wave by itself. The evidence therefore identifies two credible contributors—certification-induced kubelet/CRI load and high `rhgnr1` conntrack occupancy—but does not claim a proven root cause.

## Recommended pilot path

1. Use an HTTPS participant wave for the real concurrency proof. Invoke the 25 Multi-Agent workflows through their internal Routes, at the same time as the 25 RAG and 25 Agent 201 journeys. This matches browser/application traffic without requiring 25 simultaneous kubelet exec streams.
2. Batch the administrative deep checks at five seats. Namespace authorization, secrets-shape, Argo CD, terminal, learner-policy mutation, rollback, and residue checks remain exhaustive, but do not need to impersonate concurrent participant HTTP traffic.
3. Keep `rhgnr1` cordoned outside supervised certification windows. Re-cordon it immediately after the Multi-Agent deep-check stage.
4. Keep workshop provisioning staggered and allow participants to operate concurrently. The pilot should not advertise simultaneous rollout mutation as a participant requirement.
5. During the HTTPS-only run, compare probe deadlines, kubelet/CRI runtime-operation latency, conntrack occupancy, disk activity, model queueing, and application success. This distinguishes platform pressure from certifier pressure.
6. Inspect `rhgnr1` conntrack state in an approved node diagnostic window before changing limits. Identify stale flows or a leak first; raising `nf_conntrack_max` without understanding churn only postpones failure.
7. Replace restart-based learner configuration with dynamic policy reload after the September 17 pilot. A dynamic policy reload is the durable fix for the Track 2 configuration exercise.

## Acceptance boundary

The September 17 internal pilot can proceed only if the HTTPS-only participant wave repeatedly completes 75/75, deep checks complete 25/25 per catalog, `rhgnr1` is restored to cordoned state, and every temporary policy/certification artifact is removed. Any correlated probe wave remains visible as a RED resilience observation even if application retries recover.

Public browser access, permanent ingress/DNS, and a production SLA remain separate release gates.
