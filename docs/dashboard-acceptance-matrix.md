# Dashboard acceptance matrix

This matrix is the release contract for the external portal and internal operations/admin dashboard.

## BDD journeys

| ID | Persona | Given | When | Then | Evidence |
|---|---|---|---|---|---|
| EXT-01 | Partner user | The portal is available | They open `/` | They see catalog, active lab, request, and usage entry points | Component test + screenshot |
| EXT-02 | Partner user | They have an active session | They open its detail page | They can open the lab and see expiry, validation, and showback | Component/API contract test |
| EXT-03 | Partner user | They use the external hostname | Navigation renders | Internal fleet, decisions, feedback, and admin links are absent | Navigation contract test |
| OPS-01 | Operator | They use the admin hostname | They open `/` | Fleet health, active sessions, failures, and capacity are visible | Component/API contract test |
| OPS-02 | Operator | A session needs intervention | They open session operations | They can inspect diagnostics and perform permitted lifecycle actions | API authorization test |
| ADM-01 | Administrator | They have the admin role | They open `/admin` | Tenant/session reports and admin actions are available | Authorization + route test |
| SEC-01 | Partner user | They lack an admin role | They call an admin API | The API returns 403 | Backend authorization test |
| DEP-01 | External client | Portal and admin routes are deployed | They request each hostname | Both return HTTP 200 and the expected surface | OpenShift route evidence |

## Red/green matrix

| Contract | Red condition | Green condition |
|---|---|---|
| Surface detection | Portal and admin hostnames resolve to the same navigation | Hostname selects the correct surface |
| Navigation isolation | External users can see internal links | External navigation contains only self-service routes |
| Route isolation | External surface mounts `/admin` | Admin routes mount only on the internal surface |
| API compatibility | UI calls endpoints outside `/api/v1` proxy contract | All calls pass through `/api/*` and receive typed responses |
| Deployment | Oberon removes permanent frontends | Portal/admin deployments, services, and routes are rendered |
| Availability | Pod readiness does not prove HTTP service | Pod, service, router, and public route each return healthy evidence |

## Release rubric

Each category scores 0–2. Release requires 10/12 with no zero in Security or Availability.

- Behavior: primary external and operator journeys pass.
- Contracts: typed UI/API and route contracts pass.
- Components: navigation, summaries, states, and actions have component tests.
- Security: server-side tenant/admin authorization is enforced.
- Availability: build, pod, service, router, and public route checks pass.
- Evidence: test output and deployment observations are captured with the release.

