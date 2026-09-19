# ACM and Launchpad architecture decision

## Status

Accepted for local contract development. No ACM installation, cluster import,
policy propagation, GitOps synchronization, or live placement is authorized by
this decision.

## Decision

Use Red Hat Advanced Cluster Management as the production fleet-management and
governance layer, OpenShift GitOps as the desired-state deployment layer, and
Launchpad as the event and lab lifecycle authority.

The control flow is:

1. ACM registers managed clusters, organizes them into ManagedClusterSets,
   applies governance, and produces PlacementDecisions.
2. The Launchpad ACM adapter records an immutable snapshot of selected
   ManagedClusters, health conditions, labels, claims, and decision reasons.
3. Launchpad intersects the `acm_eligible` candidate set with its independently
   approved catalog-by-cluster capacity matrix and current reservations.
4. Launchpad persists the final cluster reference before lifecycle work begins.
5. OpenShift GitOps deploys the signed, versioned release to that persisted
   destination.
6. ACM governance and health plus Launchpad functional validation determine
   readiness; neither alone is sufficient.

## Ownership boundary

### Red Hat Advanced Cluster Management

- ManagedCluster registration, health, labels, claims, and lifecycle
- ManagedClusterSets and namespace-scoped Placements
- Governance policies, compliance, quarantine labels, and fleet visibility
- Candidate selection and prioritization signals

### OpenShift GitOps

- Versioned desired state and signed artifact deployment
- Application/ApplicationSet reconciliation to approved destinations
- Drift visibility for platform and catalog releases

### Launchpad

- Event manifests, workshops, seats, identity, TTL, and reclaim
- Exact catalog-release certification and model dependencies
- Capacity reservations and atomic workshop placement
- Persisted `cluster_ref`, participant validation, audit, and evidence

## Fail-closed rules

- ACM selection is a candidate decision, never proof of seat capacity.
- Missing ACM availability or hub acceptance excludes the cluster.
- Failure to read ACM decisions is an error, not an empty healthy fleet.
- ACM data never carries cluster credentials into Launchpad domain records.
- DR-reserved and uncertified capacity remain non-placeable.
- Active workshops are never retargeted when ACM changes a later decision.
- The local admission contract defaults to a 120-second maximum ACM snapshot
  age and 30 seconds of future clock skew. Stale or future-dated evidence is
  rejected rather than silently accepted. Production values remain an SLO and
  integration decision.

## Local admission join

`apply_acm_eligibility` intersects the approved Launchpad capacity matrix with
the fresh `acm_eligible` candidate set. It never adds capacity or changes
catalog certification. Matrix clusters absent from the candidate set are
disabled for normal placement while their DR-reserved and uncertified values
remain visible. The ACM snapshot digest and observation time travel with the
capacity decision so later reservations can prove which fleet view they used.

## Deployment shape

Use one ACM hub on the dedicated production control-plane cluster for the
initial fleet. Multicluster Global Hub is deferred until Launchpad operates
multiple ACM hubs at a scale that justifies another aggregation tier.

## Red Hat references

- [ACM cluster lifecycle and Placement](https://docs.redhat.com/en/documentation/red_hat_advanced_cluster_management_for_kubernetes/2.15/html/clusters/cluster_mce_overview)
- [ACM governance](https://docs.redhat.com/en/documentation/red_hat_advanced_cluster_management_for_kubernetes/2.14/html-single/governance)
- [ACM Multicluster Global Hub](https://docs.redhat.com/en/documentation/red_hat_advanced_cluster_management_for_kubernetes/2.14/html-single/multicluster_global_hub/index)
