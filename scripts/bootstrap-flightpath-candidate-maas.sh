#!/usr/bin/env bash
set -euo pipefail

candidate_kubeconfig="${LAUNCHPAD_FLIGHTPATH_KUBECONFIG:?set LAUNCHPAD_FLIGHTPATH_KUBECONFIG}"
candidate_namespace="${LAUNCHPAD_FLIGHTPATH_NAMESPACE:-launchpad-flightpath-candidate}"
candidate_secret="launchpad-litellm"

oc() {
  command oc --kubeconfig "$candidate_kubeconfig" "$@"
}

if oc get secret "$candidate_secret" -n "$candidate_namespace" >/dev/null 2>&1; then
  existing_master_key="$(oc get secret "$candidate_secret" -n "$candidate_namespace" -o jsonpath='{.data.LITELLM_API_KEY}')"
  existing_database_url="$(oc get secret "$candidate_secret" -n "$candidate_namespace" -o jsonpath='{.data.DATABASE_URL}')"
  if [[ -z "$existing_master_key" || -z "$existing_database_url" ]]; then
    echo "Existing candidate MaaS Secret is incomplete" >&2
    exit 1
  fi
  oc rollout status deployment/launchpad-candidate-maas \
    -n "$candidate_namespace" --timeout=240s
  echo "Existing Flightpath candidate MaaS bootstrap is healthy"
  exit 0
fi

candidate_maas_db_password="$(openssl rand -hex 24)"
candidate_maas_master_key="$(openssl rand -hex 32)"

role_exists="$(
  oc exec -n "$candidate_namespace" deployment/postgres -- sh -lc \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select 1 from pg_roles where rolname='\''litellm'\''"'
)"
if [[ "$role_exists" == "1" ]]; then
  oc exec -n "$candidate_namespace" deployment/postgres -- \
    env CANDIDATE_MAAS_DB_PASSWORD="$candidate_maas_db_password" sh -lc \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "ALTER ROLE litellm PASSWORD '\''${CANDIDATE_MAAS_DB_PASSWORD}'\''"'
else
  oc exec -n "$candidate_namespace" deployment/postgres -- \
    env CANDIDATE_MAAS_DB_PASSWORD="$candidate_maas_db_password" sh -lc \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "CREATE ROLE litellm LOGIN PASSWORD '\''${CANDIDATE_MAAS_DB_PASSWORD}'\''"'
fi

database_exists="$(
  oc exec -n "$candidate_namespace" deployment/postgres -- sh -lc \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select 1 from pg_database where datname='\''litellm'\''"'
)"
if [[ "$database_exists" != "1" ]]; then
  oc exec -n "$candidate_namespace" deployment/postgres -- sh -lc \
    'createdb -U "$POSTGRES_USER" -O litellm litellm'
else
  oc exec -n "$candidate_namespace" deployment/postgres -- sh -lc \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "ALTER DATABASE litellm OWNER TO litellm"'
fi

candidate_maas_database_url="postgresql://litellm:${candidate_maas_db_password}@postgres.${candidate_namespace}.svc:5432/litellm"
oc create secret generic "$candidate_secret" -n "$candidate_namespace" \
  --from-literal=LITELLM_API_KEY="$candidate_maas_master_key" \
  --from-literal=DATABASE_URL="$candidate_maas_database_url" \
  --dry-run=client -o yaml | oc apply -f -
oc label secret "$candidate_secret" -n "$candidate_namespace" \
  app.kubernetes.io/managed-by=launchpad-bootstrap \
  app.kubernetes.io/part-of=partner-ai-launchpad \
  --overwrite >/dev/null

oc rollout status deployment/launchpad-candidate-maas \
  -n "$candidate_namespace" --timeout=240s
oc rollout status deployment/backend \
  -n "$candidate_namespace" --timeout=240s
oc rollout status deployment/lifecycle-worker \
  -n "$candidate_namespace" --timeout=240s

echo "Flightpath candidate MaaS bootstrap completed without displaying credentials"
