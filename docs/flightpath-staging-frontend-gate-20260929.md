# Flightpath staging frontend gate — 2026-09-29

## Decision boundary

The Flightpath staging gate remains open until the complete requester,
administrator, and participant browser journey passes against the unchanged
candidate. Production-gate work, rapid cluster onboarding, impact-based quick
recertification, independent Showroom delivery, and hybrid-cloud federation
remain pinned.

## Candidate already proven

- Candidate commit: `e2d78de667096c7be6e277ec01bf6c29a4a1ffb4`
- Candidate manifest SHA-256:
  `c2aaac7b3805bd4adf3edf6f4996e30bddb11d6f16fa7eb37b42fb19477306cb`
- Eleven currently viable catalogs previously passed a cluster-native five-seat
  matrix. That result is retained as historical scale evidence; five seats are
  not required for the current certification phase.
- The final matrix reported `all_catalogs_green: true` and
  `zero_residue: true`.
- The final residue verifier found zero seat namespaces, Routes, RoleBindings,
  session Secrets, Argo CD Applications, entitlements, access policies,
  access sessions, inactive identities, and session credentials created by the
  run.
- The complete immutable proof set is retained under
  `evidence/runs/staging-candidate-e2d78de/`: eleven catalog bundles, the final
  zero-residue bundle, and one verified SHA-256 sidecar for every JSON
  artifact. Every catalog bundle records five seats, `GREEN-live`, a 100-point
  rubric, completed cleanup, and zero counted cleanup resources.

## Frontend and contract evidence

The following checks passed from the unchanged repository candidate on
2026-09-29:

| Layer | Result |
| --- | --- |
| Requester component tests | 18 files, 66 tests passed |
| Requester production build | passed |
| Admin component tests | 4 files, 8 tests passed |
| Admin production build | passed |
| Portal/API CDD, workshop order, participant journey, and response-security tests | 93 tests passed |

These results are GREEN-local/GREEN-integration. They do not substitute for a
browser journey through deployed ingress, OAuth, routes, Showroom, tools, and
reclaim.

The deployed candidate services were also probed from inside the
`launchpad-flightpath-candidate` namespace. The requester and admin application
ports returned their HTML entry documents with HTTP 200; backend `/health`
returned HTTP 200; and backend `/openapi.json` returned the Launchpad OpenAPI
document with HTTP 200. The externally protected service ports correctly
returned HTTP 403 without an authenticated identity. This proves the deployed
applications are reachable behind the edge, but it does not satisfy the
authenticated browser requirement.

## Live browser blocker

The live browser journey is RED-blocked before authentication:

- `launchpad-candidate.apps.flightpath.fm2aihpcsed.com` resolves to
  `192.168.1.246` but presents the cluster-generated
  `*.apps.flightpath.fm2aihpcsed.com` certificate issued by
  `ingress-operator@1776985796`; it is not trusted by the managed browser.
- `launchpad-api-candidate.apps.flightpath.fm2aihpcsed.com` has the same
  untrusted certificate condition.
- `launchpad-admin-candidate.apps.flightpath.fm2aihpcsed.com` resolves to
  `192.168.1.245`, where TCP 443 is refused. The requester and API names resolve
  to `192.168.1.246`, where TCP 443 responds. Resolving the admin hostname
  temporarily to `192.168.1.246` produced the expected authenticated-edge HTTP
  403 response, proving the admin Route is present behind the working ingress
  address and the remaining reachability defect is the admin DNS target.
- `https://labs.smg-helix.ai/health` returns HTTP 200 with trusted TLS, but this
  origin is the participant access gateway and is not a substitute for the
  authenticated requester and administrator portals.

No certificate warning was bypassed and no new workshop was created while the
browser entry point was untrusted.

## Public one-seat browser progress

The stable participant origin is no longer a blanket blocker for public lab
certification. On the unchanged public-access backend release, the following
catalogs passed the external email-and-code journey with trusted TLS, claim,
same-seat recovery, participant navigation, namespace isolation, logout/resume,
normal reclaim, and zero residue:

- `sovereign-ai-101`
- `virtualization-ai-301`

These results prove the participant edge and the two named catalog journeys.
They do **not** close the frontend staging gate: the authenticated requester and
administrator portals, manual order creation, workshop/session reconciliation,
all remaining viable catalogs, add-lab permutations, namespace-scoped Console,
and the final unchanged-candidate browser sweep are still open.

### Shared-origin shortcut rejected

`labs.smg-helix.ai` cannot safely substitute for the requester and
administrator hostnames in the unchanged candidate. The named-tunnel router
currently sends every non-Keycloak/non-Console path to the participant access
gateway. The requester, administrator, and API services each use a distinct
OpenShift OAuth proxy and a ServiceAccount redirect reference bound to their
own Route. Mounting those applications under new shared-origin path prefixes
would therefore require new router dispatch, prefix-aware application builds,
and changed OAuth redirect ownership. It could also collapse the intentional
participant/API trust boundary. That is a candidate change, not a DNS repair,
and is excluded from this gate.

The authoritative recheck on 2026-09-29 found the requester and API endpoints
responding behind the Flightpath ingress but still presenting the untrusted
cluster-generated certificate. The administrator endpoint still refused TCP
443. The participant origin continued to present a trusted Let's Encrypt
certificate. No live routing or OAuth configuration was changed during this
assessment.

## Required live acceptance after ingress is corrected

Using one one-seat order created through the requester UI:

1. Prove catalog visibility, capacity preview, order confirmation, and selected
   Flightpath cluster.
2. Prove the workshop and its one seat state in requester and admin views.
3. Claim a participant seat and prove My Labs, Open Lab, Showroom, workspace,
   terminal, namespace-scoped Console, resume, add-lab, and logout behavior.
4. Prove catalog-specific learner functionality and truthful failures.
5. Reclaim through the admin UI, repeat the reclaim idempotently, and verify
   zero namespaces, Routes, RoleBindings, Applications, Secrets, storage,
   credentials, access records, or inactive identities remain.
6. Capture screenshots and bind the result to the unchanged candidate identity.

Only after this journey is GREEN-live may the staging evidence manifest be
assembled and explicit staging acceptance requested.

## October 6 convergence result

The unchanged Flightpath candidate now passes the requester, administrator,
workshop, and public participant browser journey. The one-seat internal and
public Agentic AI 101 canaries proved capacity preview, order creation,
workshop/session visibility, email-and-code claim, same-seat recovery, My Labs,
add-lab control presence, logout, Showroom, Interactive Story, Terminal,
namespace-scoped OpenShift Console, own-namespace access, cross-namespace and
cluster-scope denial, aggregate reclaim, and zero workload residue.

The exercise also found and corrected one administrator lifecycle defect:
force-reclaiming a workshop seat directly left the parent workshop ready. The
deployed correction now routes that action through the parent workshop
lifecycle; the live retest left the workshop completed, its seat and session
reclaimed, and no namespace, Route, RoleBinding, or Argo CD Application.

The staging gate is reduced to one security boundary. OpenShift retains OAuth
access tokens and a User object after Launchpad disables the participant's
final identity. Namespace deletion and RoleBinding removal deny effective lab
access, but the accepted gate requires zero inactive identity residue. The
candidate must therefore remain unqualified until least-privilege token
revocation and disabled-user lifecycle cleanup are implemented and proven.

The immutable evidence is
`evidence/convergence/staging-workshop-public-canary-20261006.yaml`.
