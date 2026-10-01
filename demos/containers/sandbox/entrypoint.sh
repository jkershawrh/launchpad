#!/bin/bash

set -euo pipefail

ACCESS_METHODS=",${ACCESS_METHODS:-ssh},"
service_pids=()
WORKSPACE=/home/lab-user/workspace
if ! mkdir -p "$WORKSPACE" 2>/dev/null || [[ ! -w "$WORKSPACE" ]]; then
  echo "Persistent workspace is not writable for this OpenShift UID; using an ephemeral workspace."
  WORKSPACE=/tmp/launchpad-workspace
  mkdir -p "$WORKSPACE"
fi
mkdir -p /tmp/launchpad-sshd

# Seed the optional guided start without replacing anything the learner has
# already created in the persistent workspace.
if [[ ! -e "$WORKSPACE/GETTING_STARTED.md" ]]; then
  cp /opt/launchpad/guided-start.md "$WORKSPACE/GETTING_STARTED.md"
fi

if [[ -n "${SANDBOX_NAMESPACE:-}" && -r /var/run/secrets/kubernetes.io/serviceaccount/token ]]; then
  export KUBECONFIG="${KUBECONFIG:-/tmp/launchpad-kubeconfig}"
  oc config set-cluster in-cluster \
    --server="https://${KUBERNETES_SERVICE_HOST}:${KUBERNETES_SERVICE_PORT_HTTPS}" \
    --certificate-authority=/var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
    --embed-certs=true >/dev/null
  oc config set-credentials sandbox-user \
    --token="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)" >/dev/null
  oc config set-context sandbox \
    --cluster=in-cluster --user=sandbox-user --namespace="$SANDBOX_NAMESPACE" >/dev/null
  oc config use-context sandbox >/dev/null
  chmod 600 "$KUBECONFIG"
fi

if [[ "$ACCESS_METHODS" == *,ssh,* ]]; then
  echo "Starting SSH server on port 2222..."
  ssh-keygen -q -t ed25519 -N '' -f /tmp/launchpad-sshd/host_key
  cat >/tmp/launchpad-sshd/sshd_config <<EOF
Port 2222
ListenAddress 0.0.0.0
HostKey /tmp/launchpad-sshd/host_key
PidFile /tmp/launchpad-sshd/sshd.pid
UsePAM no
PasswordAuthentication no
PermitRootLogin no
StrictModes no
AuthorizedKeysFile none
Subsystem sftp internal-sftp
EOF
  /usr/sbin/sshd -D -e -f /tmp/launchpad-sshd/sshd_config &
  service_pids+=("$!")
fi

if [[ "$ACCESS_METHODS" == *,vscode,* ]]; then
  : "${SSH_PASSWORD:?SSH_PASSWORD is required for browser IDE access}"
  echo "Starting code-server on port 8443..."
  PASSWORD="$SSH_PASSWORD" code-server \
    --bind-addr 0.0.0.0:8443 --auth password --disable-telemetry "$WORKSPACE" &
  service_pids+=("$!")
fi

STACK_LEVEL="${STACK_LEVEL:-minimal}"

echo ""
echo "============================================"
echo "  Partner AI Launchpad — Sandbox Ready"
echo "============================================"
echo "  Stack: $STACK_LEVEL"
echo "  SSH:   ssh lab-user@localhost -p 2222"
echo "  MaaS:  $MODEL_ENDPOINT"
echo "============================================"
echo ""

if (( ${#service_pids[@]} > 0 )); then
  wait -n "${service_pids[@]}"
else
  # Console and Web Terminal are hosted by OpenShift, not this pod. Keep the
  # namespace workspace alive when no local access service was requested.
  sleep infinity
fi
