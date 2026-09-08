#!/usr/bin/env bash
set -euo pipefail
umask 077

namespace="partner-ai-launchpad"
work_dir="$(mktemp -d)"

cleanup() {
  rm -f "$work_dir/launchpad.dump"
  rmdir "$work_dir" 2>/dev/null || true
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

require_tools() {
  for tool in oc age shasum; do
    command -v "$tool" >/dev/null || fail "$tool is required"
  done
}

postgres_pod() {
  local cluster_kubeconfig="$1"
  KUBECONFIG="$cluster_kubeconfig" oc -n "$namespace" get pods \
    -l app.kubernetes.io/name=postgres \
    --field-selector=status.phase=Running \
    -o jsonpath='{.items[0].metadata.name}'
}

verify_checksum() {
  local encrypted_backup="$1"
  local checksum_file="$2"
  local backup_dir backup_name expected actual
  backup_dir="$(cd "$(dirname "$encrypted_backup")" && pwd)"
  backup_name="$(basename "$encrypted_backup")"
  expected="$(awk -v name="$backup_name" '$2 == name {print $1}' "$checksum_file")"
  [[ -n "$expected" ]] || fail "checksum file has no entry for $backup_name"
  actual="$(shasum -a 256 "$backup_dir/$backup_name" | awk '{print $1}')"
  [[ "$actual" == "$expected" ]] || fail "encrypted backup checksum mismatch"
}

backup_database() {
  local cluster_kubeconfig="$1"
  local encrypted_backup="$2"
  local age_recipient="$3"
  local server role pod backup_dir backup_name checksum_file
  [[ -f "$cluster_kubeconfig" ]] || fail "source kubeconfig is not a file"
  server="$(KUBECONFIG="$cluster_kubeconfig" oc whoami --show-server)"
  role="$(KUBECONFIG="$cluster_kubeconfig" oc -n "$namespace" get configmap launchpad-config -o jsonpath='{.data.LAUNCHPAD_CONTROL_PLANE_ROLE}')"
  [[ "$role" == "active" ]] || fail "refusing to back up a non-active control plane at $server"
  pod="$(postgres_pod "$cluster_kubeconfig")"
  [[ -n "$pod" ]] || fail "no running PostgreSQL pod found"

  KUBECONFIG="$cluster_kubeconfig" oc -n "$namespace" exec "$pod" -- sh -c \
    'exec pg_dump --format=custom --no-owner --no-acl --username="$POSTGRES_USER" "$POSTGRES_DB"' \
    > "$work_dir/launchpad.dump"
  KUBECONFIG="$cluster_kubeconfig" oc -n "$namespace" exec -i "$pod" -- \
    pg_restore --list < "$work_dir/launchpad.dump" >/dev/null

  backup_dir="$(dirname "$encrypted_backup")"
  backup_name="$(basename "$encrypted_backup")"
  mkdir -p "$backup_dir"
  age --encrypt -r "$age_recipient" -o "$encrypted_backup" "$work_dir/launchpad.dump"
  checksum_file="$encrypted_backup.sha256"
  (cd "$backup_dir" && shasum -a 256 "$backup_name" > "$(basename "$checksum_file")")
  echo "Encrypted backup: $encrypted_backup"
  echo "Checksum: $checksum_file"
  echo "Source: $server"
}

restore_database() {
  local cluster_kubeconfig="$1"
  local encrypted_backup="$2"
  local checksum_file="$3"
  local age_identity="$4"
  local confirmation="$5"
  local server role pod active_writers unsuspended_schedulers
  local actual_infrastructure actual_db_system_id expected_confirmation
  [[ -f "$cluster_kubeconfig" ]] || fail "target kubeconfig is not a file"
  [[ -f "$encrypted_backup" ]] || fail "encrypted backup is not a file"
  [[ -f "$checksum_file" ]] || fail "checksum file is not a file"
  [[ -f "$age_identity" ]] || fail "age identity is not a file"

  server="$(KUBECONFIG="$cluster_kubeconfig" oc whoami --show-server)"
  [[ "$server" == "https://api.flightpath.fm2aihpcsed.com:6443" ]] \
    || fail "restore target is not Flightpath: $server"
  actual_infrastructure="$(KUBECONFIG="$cluster_kubeconfig" oc get infrastructure cluster -o jsonpath='{.status.infrastructureName}')"
  [[ -n "$actual_infrastructure" ]] || fail "Flightpath infrastructureName is unavailable"
  role="$(KUBECONFIG="$cluster_kubeconfig" oc -n "$namespace" get configmap launchpad-config -o jsonpath='{.data.LAUNCHPAD_CONTROL_PLANE_ROLE}')"
  [[ "$role" == "standby" ]] || fail "Flightpath must still be standby during restore"

  active_writers="$(KUBECONFIG="$cluster_kubeconfig" oc -n "$namespace" get deployments backend lifecycle-worker -o jsonpath='{range .items[?(@.spec.replicas>0)]}{.metadata.name}{"\n"}{end}')"
  [[ -z "$active_writers" ]] || fail "Flightpath writers are already active: $active_writers"
  unsuspended_schedulers="$(KUBECONFIG="$cluster_kubeconfig" oc -n "$namespace" get cronjob lifecycle-scheduler -o jsonpath='{.spec.suspend}')"
  [[ "$unsuspended_schedulers" == "true" ]] || fail "Flightpath lifecycle scheduler is active"

  verify_checksum "$encrypted_backup" "$checksum_file"
  pod="$(postgres_pod "$cluster_kubeconfig")"
  [[ -n "$pod" ]] || fail "start only the Flightpath PostgreSQL deployment before restore"
  actual_db_system_id="$(KUBECONFIG="$cluster_kubeconfig" oc -n "$namespace" exec "$pod" -- sh -c \
    'pg_controldata "$PGDATA" | awk -F: '\''/Database system identifier/ {gsub(/[[:space:]]/, "", $2); print $2}'\''')"
  [[ "$actual_db_system_id" =~ ^[0-9]+$ ]] || fail "Flightpath database system identifier is unavailable"
  expected_confirmation="--confirm-target=flightpath:${actual_infrastructure}:${actual_db_system_id}"
  [[ "$confirmation" == "$expected_confirmation" ]] || {
    echo "Restore confirmation must bind Flightpath infrastructure and database identities." >&2
    echo "Required confirmation: $expected_confirmation" >&2
    exit 1
  }

  age --decrypt -i "$age_identity" -o "$work_dir/launchpad.dump" "$encrypted_backup"
  KUBECONFIG="$cluster_kubeconfig" oc -n "$namespace" exec -i "$pod" -- \
    pg_restore --list < "$work_dir/launchpad.dump" >/dev/null
  KUBECONFIG="$cluster_kubeconfig" oc -n "$namespace" exec -i "$pod" -- sh -c \
    'exec pg_restore --clean --if-exists --exit-on-error --no-owner --no-acl --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
    < "$work_dir/launchpad.dump"
  echo "Restore completed on $server; keep all writers stopped until reconciliation review."
}

require_tools
case "${1:-}" in
  backup)
    [[ $# -eq 4 ]] || fail "usage: $0 backup KUBECONFIG OUTPUT.dump.age AGE_RECIPIENT"
    backup_database "$2" "$3" "$4"
    ;;
  verify)
    [[ $# -eq 3 ]] || fail "usage: $0 verify OUTPUT.dump.age OUTPUT.dump.age.sha256"
    verify_checksum "$2" "$3"
    echo "Encrypted backup checksum: GREEN"
    ;;
  restore)
    [[ $# -eq 6 ]] || fail "usage: $0 restore KUBECONFIG BACKUP CHECKSUM AGE_IDENTITY --confirm-target=flightpath:INFRASTRUCTURE_ID:DATABASE_SYSTEM_ID"
    restore_database "$2" "$3" "$4" "$5" "$6"
    ;;
  *)
    fail "expected backup, verify, or restore"
    ;;
esac
