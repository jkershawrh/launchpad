#!/usr/bin/env bash
set -uo pipefail

: "${LAUNCHPAD_ADMIN_API_KEY:?LAUNCHPAD_ADMIN_API_KEY is required}"
: "${LAUNCHPAD_CANDIDATE_GIT_COMMIT:?LAUNCHPAD_CANDIDATE_GIT_COMMIT is required}"
: "${LAUNCHPAD_CANDIDATE_MANIFEST_SHA256:?LAUNCHPAD_CANDIDATE_MANIFEST_SHA256 is required}"
: "${LAUNCHPAD_CERTIFICATION_RUNNER_IMAGE:?LAUNCHPAD_CERTIFICATION_RUNNER_IMAGE is required}"
: "${DATABASE_URL:?DATABASE_URL is required for final residue verification}"

api_base_url="${LAUNCHPAD_API_BASE_URL:-http://backend:8000}"
tenant_id="${LAUNCHPAD_CERTIFICATION_TENANT:-flightpath-candidate-cert}"
owner_id="${LAUNCHPAD_CERTIFICATION_OWNER:-flightpath-native-certifier}"
evidence_dir="${LAUNCHPAD_EVIDENCE_DIR:-/evidence/catalog}"
run_series="${LAUNCHPAD_RUN_PREFIX:-flightpath-staging}"
run_attempt="${LAUNCHPAD_RUN_ATTEMPT:-$(date -u +%Y%m%dT%H%M%SZ)-${HOSTNAME##*-}}"
run_prefix="${run_series}-${run_attempt}"
cluster_api="${LAUNCHPAD_CLUSTER_API:-https://api.flightpath.fm2aihpcsed.com:6443}"
ca_bundle="${LAUNCHPAD_CA_BUNDLE:-}"
matrix="${LAUNCHPAD_CERTIFICATION_MATRIX:-agent-reliability ai-sandbox cpu-inference-serving hybrid-fraud-detection intel-llm-cpu-serving intel-llm-tool-calling intel-xeon6-agent-201 multi-agent-quickstart-flightpath network-operations-agent openshift-operators-workshop rag-on-xeon}"
certification_seats="${LAUNCHPAD_CERTIFICATION_SEATS:-1}"
run_started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if ! [[ "${certification_seats}" =~ ^[1-9][0-9]*$ ]]; then
  echo "LAUNCHPAD_CERTIFICATION_SEATS must be a positive integer" >&2
  exit 2
fi

mkdir -p "${evidence_dir}"
umask 077
cat > /tmp/flightpath-kubeconfig <<EOF
apiVersion: v1
kind: Config
clusters:
- name: flightpath
  cluster:
    certificate-authority: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
    server: ${cluster_api}
contexts:
- name: flightpath
  context:
    cluster: flightpath
    namespace: launchpad-flightpath-candidate
    user: certification-runner
current-context: flightpath
users:
- name: certification-runner
  user:
    tokenFile: /var/run/secrets/kubernetes.io/serviceaccount/token
EOF
export KUBECONFIG=/tmp/flightpath-kubeconfig

declare -a failed=()
for contract_name in ${matrix}; do
  catalog_id="${contract_name%-flightpath}"
  contract="certification/catalog/${contract_name}.yaml"
  intake="catalog-onboarding/${contract_name}.yaml"
  if [[ ! -f "${intake}" ]]; then
    intake="catalog-onboarding/${catalog_id}.yaml"
  fi
  run_id="${run_prefix}-${catalog_id}-${certification_seats}-seat"
  output="${evidence_dir}/${run_id}.json"
  ca_args=()
  if [[ -n "${ca_bundle}" ]]; then
    ca_args=(--ca-bundle "${ca_bundle}")
  fi
  echo "certification_start catalog=${catalog_id} candidate=${LAUNCHPAD_CANDIDATE_GIT_COMMIT}"
  if ! python scripts/catalog_certification.py run \
      "${contract}" \
      --intake "${intake}" \
      --seats "${certification_seats}" \
      --api-base-url "${api_base_url}" \
      --api-key-env LAUNCHPAD_ADMIN_API_KEY \
      --tenant-id "${tenant_id}" \
      --owner-id "${owner_id}" \
      --ttl 2h \
      --run-id "${run_id}" \
      --output "${output}" \
      "${ca_args[@]}" \
      --poll-interval 5; then
    failed+=("${catalog_id}")
  fi
done

python scripts/verify_staging_zero_residue.py \
  --evidence-dir "${evidence_dir}" \
  --candidate-commit "${LAUNCHPAD_CANDIDATE_GIT_COMMIT}" \
  --manifest-sha256 "${LAUNCHPAD_CANDIDATE_MANIFEST_SHA256}" \
  --run-prefix "${run_prefix}" \
  --run-started-at "${run_started_at}" \
  --output "${evidence_dir}/${run_prefix}-zero-residue.json"
residue_rc=$?

if (( ${#failed[@]} > 0 || residue_rc != 0 )); then
  printf 'certification_matrix_failed catalogs=%s residue_rc=%s\n' "${failed[*]:-none}" "${residue_rc}" >&2
  exit 1
fi
echo "certification_matrix_green catalogs=11 seats=${certification_seats}"
