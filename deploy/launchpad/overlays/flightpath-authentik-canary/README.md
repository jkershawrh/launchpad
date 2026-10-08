# Flightpath Authentik workforce-access canary

This overlay adds **new** requester and admin routes. It does not replace the
current OpenShift-authenticated routes and does not change participant
Keycloak, lab-code claims, OpenShift Console identity, provisioning, or lab
runtime resources.

Do not apply this overlay until all prerequisites pass:

1. `auth.smg-helix.ai` resolves to a durable Authentik service with trusted TLS.
2. Authentik has one confidential OIDC provider with client ID
   `launchpad-workforce`, issuer slug `launchpad-workforce`, and both exact
   callback URLs from `workforce-proxies.yaml`.
3. The provider emits `preferred_username`, `email`, and a list-valued `groups`
   claim. Group membership is invitation-only.
4. The namespace contains a secret named `launchpad-authentik-workforce` with
   keys `client-id`, `client-secret`, `requester-cookie-secret`, and
   `admin-cookie-secret`. Secrets are generated and stored out of band; no
   plaintext values belong in Git.
5. PostgreSQL backup/restore, Authentik break-glass access, MFA for privileged
   groups, and user-disable behavior have evidence.

The canary routes are:

- `https://launchpad-auth-candidate.apps.flightpath.fm2aihpcsed.com`
- `https://launchpad-admin-auth-candidate.apps.flightpath.fm2aihpcsed.com`

The admin proxy additionally requires `launchpad-admins`. Backend APIs verify
the signed token again and derive tenant access from groups named
`launchpad-tenant:<tenant-id>`.

Render without applying:

```sh
oc kustomize deploy/launchpad/overlays/flightpath-authentik-canary >/tmp/launchpad-authentik-canary.yaml
```

Promotion is forbidden until the validation matrix in
`docs/authentik-workforce-access.md` is green. Applying the overlay restarts the
backend so it can load the OIDC verifier configuration; schedule that canary
test after current lab validation is complete.
