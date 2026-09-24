# Portal/API Contract and Promotion Gate

The requester and operations portals use the same same-origin API rule:

- browser request: `/api/<resource>`
- Nginx translation: `/api/` to backend `/api/v1/`
- FastAPI provider: `/api/v1/<resource>`

Portal code must never insert another `/v1`. The executable contract in
`contracts/portal-api-cdd-v1.yaml` and
`backend/tests/test_portal_api_cdd.py` inventories every `request()` and
direct `fetch()` path in both portals, resolves it against the backend OpenAPI
document, and verifies the critical mutation methods.

## Deployment gate

A local green result is necessary but does not certify a deployed platform.
For one immutable candidate commit and image set, promotion requires:

1. requester and admin unit tests and production builds;
2. backend consumer/provider, lifecycle, workshop, and public-access tests;
3. deterministic Kustomize rendering and secret scanning;
4. candidate deployment using the exact tested image digests;
5. authenticated requester and admin route probes;
6. one individual lab create, queued provision, status polling, validation,
   Showroom/workspace access, and reclaim;
7. one workshop capacity preview and order contract check;
8. zero-residue namespace, Route, RoleBinding, Application, model-key, and
   lifecycle-job reconciliation.

The live journey is repeated after deployment because repository tests cannot
prove cluster ingress, OAuth identity, image pull, model reachability,
Showroom content, or cleanup behavior.

## YAML cleanup boundary

YAML cleanup follows the API correction as its own reversible change set.
Before removal or consolidation, render every active overlay, map each manifest
to its consumer, and preserve current catalog IDs, Routes, Secret references,
RBAC, lifecycle jobs, and Flightpath placement. Historical and unreferenced
manifests may be removed only after the consumer inventory and rendered-output
comparison are green. YAML cleanup must not be combined with a live candidate
deployment or an active-lab mutation.
