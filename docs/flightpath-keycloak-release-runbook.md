# Flightpath Keycloak release and landing-page promotion

This runbook promotes the passwordless participant login theme without
rebuilding the image inside an execution cluster. It does not change catalog
items, participant entitlements, workshop state, or the public tunnel.

## Build and publish without cluster access

1. Commit the reviewed authenticator and theme change.
2. Dispatch `.github/workflows/keycloak-release.yml` with the exact 40-character
   source revision and `publish: true`.
3. Require the authenticator contracts, image build, fixable high/critical
   vulnerability gate, SBOM, keyless signature, GitHub provenance attestation,
   and immutable release receipt to pass.
4. Download `keycloak-release.json`. Never substitute a mutable tag for its
   digest-pinned image reference.

The release workflow can run without the Intel VPN. It cannot deploy anything.

## Promote when Flightpath access is restored

Use a dedicated Flightpath kubeconfig and the downloaded receipt:

```text
bash scripts/promote-flightpath-keycloak.sh \
  /secure/flightpath.kubeconfig \
  /secure/keycloak-release.json
```

The script fails closed unless the API server is Flightpath, the receipt binds
an exact source revision to an approved `ghcr.io/rhpds/launchpad-keycloak`
digest, the platform is Linux/AMD64, and GitHub verifies its build attestation.
It then updates only `keycloak/keycloak.spec.image`, waits for the operator to
report the Keycloak resource Ready, and confirms that the public login contains
the platform overview and access form.

## Rollback

Record the current digest printed by the promotion script. If login, OIDC, or
claim validation fails, patch `keycloak/keycloak.spec.image` back to that exact
digest, wait for Ready, and repeat the existing login and entitlement smoke
checks. Do not roll back with a mutable tag.

