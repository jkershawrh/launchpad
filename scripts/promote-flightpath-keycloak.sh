#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
kubeconfig="${1:-}"
release_receipt="${2:-}"
namespace="keycloak"

fail() {
  printf 'flightpath Keycloak promotion blocked: %s\n' "$*" >&2
  exit 1
}

[[ -n "$kubeconfig" && -f "$kubeconfig" ]] \
  || fail "usage: $0 /explicit/flightpath.kubeconfig /path/to/keycloak-release.json"
[[ -n "$release_receipt" && -f "$release_receipt" ]] \
  || fail "release receipt is not a file"

server="$(oc --kubeconfig "$kubeconfig" whoami --show-server)"
[[ "$server" == "https://api.flightpath.fm2aihpcsed.com:6443" ]] \
  || fail "kubeconfig is not Flightpath"

schema="$(jq -r '.schema_version // empty' "$release_receipt")"
source_revision="$(jq -r '.source_revision // empty' "$release_receipt")"
image="$(jq -r '.image // empty' "$release_receipt")"
platform="$(jq -r '.platform // empty' "$release_receipt")"
published="$(jq -r '.published // false' "$release_receipt")"

[[ "$schema" == "launchpad.redhat.com/keycloak-release/v1" ]] \
  || fail "unexpected receipt schema"
[[ "$source_revision" =~ ^[0-9a-f]{40}$ ]] \
  || fail "source revision is not immutable"
[[ "$image" =~ ^ghcr\.io/rhpds/launchpad-keycloak@sha256:[0-9a-f]{64}$ ]] \
  || fail "image is not an approved immutable GHCR reference"
[[ "$platform" == "linux/amd64" && "$published" == "true" ]] \
  || fail "release is not a published linux/amd64 artifact"

command -v gh >/dev/null || fail "gh is required for attestation verification"
command -v cosign >/dev/null || fail "cosign is required for signature verification"
gh attestation verify "oci://$image" --repo rhpds/launchpad >/dev/null \
  || fail "GitHub build attestation verification failed"
cosign verify "$image" \
  --certificate-identity-regexp \
  '^https://github.com/rhpds/launchpad/.github/workflows/keycloak-release.yml@refs/(heads|tags)/.+' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com >/dev/null \
  || fail "keyless signature verification failed"

current_image="$(oc --kubeconfig "$kubeconfig" -n "$namespace" \
  get keycloak keycloak -o jsonpath='{.spec.image}')"
printf 'Current image: %s\n' "$current_image"
printf 'Candidate image: %s\n' "$image"

oc --kubeconfig "$kubeconfig" -n "$namespace" patch keycloak keycloak \
  --type=merge --patch "$(jq -nc --arg image "$image" '{spec:{image:$image}}')" >/dev/null

oc --kubeconfig "$kubeconfig" -n "$namespace" wait \
  --for=condition=Ready keycloak/keycloak --timeout=10m

login_html="$(curl -fsSL --max-time 30 https://labs.smg-helix.ai/)"
grep -Fq "What you can do in Launchpad" <<<"$login_html" \
  || fail "public login does not contain the catalog overview"
grep -Fq "Access your lab" <<<"$login_html" \
  || fail "public login does not contain the access form"

printf 'Flightpath Keycloak promotion passed for source %s.\n' "$source_revision"
