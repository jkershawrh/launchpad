#!/bin/bash

set -euo pipefail

ACCESS_METHODS=",${ACCESS_METHODS:-ssh},"
WORKSPACE=/home/lab-user/workspace
if ! mkdir -p "$WORKSPACE" 2>/dev/null || [[ ! -w "$WORKSPACE" ]]; then
  echo "Persistent workspace is not writable for this OpenShift UID; using an ephemeral workspace."
  WORKSPACE=/tmp/launchpad-workspace
  mkdir -p "$WORKSPACE"
fi
mkdir -p /tmp/launchpad-sshd

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
fi

if [[ "$ACCESS_METHODS" == *,jupyter,* || "$ACCESS_METHODS" == *,web_console,* ]]; then
  echo "Starting JupyterLab on port 8888..."
  jupyter lab --no-browser --ip=0.0.0.0 --port=8888 \
    --ServerApp.root_dir="$WORKSPACE" \
    --ServerApp.token="${SSH_PASSWORD:-launchpad}" \
    --ServerApp.allow_remote_access=True &
fi

if [[ "$ACCESS_METHODS" == *,vscode,* ]]; then
  echo "Starting code-server on port 8443..."
  PASSWORD="${SSH_PASSWORD:-launchpad}" code-server \
    --bind-addr 0.0.0.0:8443 --auth password --disable-telemetry "$WORKSPACE" &
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

wait -n
