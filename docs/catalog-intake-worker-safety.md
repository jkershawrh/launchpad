# Isolated catalog-intake worker safety contract

The repository-owned policy in `contracts/catalog-intake-worker-safety-v1.yaml` defines the minimum security boundary for any future automated catalog-intake worker. It is an analysis-only contract: it does not deploy a worker, grant credentials, publish catalog content, or mutate a live cluster.

The contract fails closed around four boundaries:

1. Sources must use HTTPS, an exact 40-character Git commit, and either an explicit repository allowlist entry or a recorded approval before fetch.
2. The worker has no user, catalog, registry-publisher, model, Argo CD, Keycloak, tunnel, or cluster credentials. Its egress defaults to deny and only permits the approved GitHub source paths.
3. Execution is non-root, unprivileged, read-only, bounded by time and resources, and uses a unique ephemeral workspace that is cleaned on every outcome.
4. Payload, fetched source, and generated evidence are secret-scanned. Logs are bounded and sanitized, and a credential-free cleanup receipt is mandatory before retry.

Validation is local and deterministic:

```bash
python scripts/validate_catalog_intake_worker_safety.py \
  --output evidence/runs/catalog-intake-worker-safety/report.json
pytest -q scripts/tests/test_validate_catalog_intake_worker_safety.py
```

The local contract can be green while release remains blocked. A production worker stays ineligible until live evidence proves the runtime security context, default-deny network enforcement, scanner failure behavior, and cleanup fault behavior.

## Discovery worker implementation boundary

The first executable slice is defined by
`contracts/catalog-intake-discovery-worker-v1.yaml`. It accepts one approved,
pinned Quickstart repository, uses a unique bounded workspace, scans the entire
checkout, runs repository discovery, emits one bounded sanitized receipt, and
always reports cleanup. Its Kubernetes Job specification has no service-account
token or Secret mounts and can reach only OpenShift DNS and a separately
approved egress proxy. It cannot reach the Kubernetes API, Launchpad database,
catalog publisher, registry publisher, workshops, or execution clusters.

This slice is deliberately not wired to the admin action yet. The worker image,
egress proxy, trusted dispatcher/receipt collector, and live fault tests must be
available before the read-only Intake pipeline can truthfully enable **Run
discovery**. Until then, the UI and API continue to report the worker as
unavailable and every mutation remains disabled.
