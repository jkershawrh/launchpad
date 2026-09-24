# Flightpath trusted TLS change request

## Outcome requested

Provide a browser-trusted certificate path for the Flightpath Launchpad
requester, admin, and API surfaces without weakening TLS verification or
changing participant workloads.

Current hosts:

- `launchpad-candidate.apps.flightpath.fm2aihpcsed.com`
- `launchpad-admin-candidate.apps.flightpath.fm2aihpcsed.com`
- `launchpad-api-candidate.apps.flightpath.fm2aihpcsed.com`

The Routes are admitted and return the expected OpenShift OAuth challenge, but
the default ingress certificate is issued by the OpenShift ingress operator.
External verification fails with `self signed certificate in certificate
chain`. Flightpath has no configured default ingress certificate and no
cert-manager API is currently installed.

## Recommended bounded change

Use an infrastructure-owned certificate for
`*.apps.flightpath.fm2aihpcsed.com` only if the platform owner approves changing
the default certificate for every application Route on Flightpath. The change
requires:

1. a publicly trusted wildcard certificate and complete chain;
2. a TLS Secret in `openshift-ingress` created through the approved secret
   delivery process;
3. an explicit change window and rollback owner;
4. an update to the default IngressController certificate reference; and
5. verification of representative existing Routes before and after the change.

If a cluster-wide wildcard is not approved, use a dedicated Launchpad ingress
domain and ingress-controller shard with its own trusted wildcard certificate.
That option adds DNS and router capacity work but limits certificate blast
radius. Do not embed private keys in Route YAML or this repository.

The existing `labs.smg-helix.ai` Cloudflare edge remains suitable for public
participant access, but it does not make the direct Flightpath `.apps` hosts
browser-trusted and must not be counted as this gate.

## Acceptance evidence

Run:

```sh
python scripts/preflight_flightpath_tls.py
```

The gate passes only when all three hosts resolve, complete a default-trust TLS
handshake with hostname verification, retain at least 30 days of validity, and
return an HTTP status below 500 without `-k`, a custom CA, or a browser warning.
Then complete authenticated requester, admin, API, OIDC redirect, logout, and
one order/reclaim browser journeys before advancing the staging candidate.
