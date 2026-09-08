#!/usr/bin/env bash
set -euo pipefail

ARENA_KUBECONFIG="${ARENA_KUBECONFIG:-/Users/jkershaw/.kube/config-arena}"
export KUBECONFIG="$ARENA_KUBECONFIG"
NAMESPACE="partner-ai-launchpad"

infrastructure=$(oc get infrastructure cluster -o jsonpath='{.status.infrastructureName}') \
  || { printf 'Arena API is unreachable; connect the VPN and retry\n' >&2; exit 1; }
[[ "$infrastructure" == arena-* ]] \
  || { printf "Refusing cluster '%s'; this workflow is Arena-only\n" "$infrastructure" >&2; exit 1; }

cluster_config=$(oc get configmap launchpad-cluster-targets -n "$NAMESPACE" \
  -o jsonpath='{.data.clusters\.yaml}')
cluster_patch=$(CLUSTER_CONFIG="$cluster_config" python3 -c '
import json
import os

import yaml

config = yaml.safe_load(os.environ["CLUSTER_CONFIG"])
arena = [cluster for cluster in config.get("clusters", []) if cluster.get("cluster_id") == "arena"]
if len(arena) != 1:
    raise SystemExit("Expected exactly one Arena cluster target")
cluster = arena[0]
cluster["public_console_url"] = ""
cluster["public_oauth_url"] = ""
cluster["public_ingress_domain"] = ""
print(json.dumps({"data": {"clusters.yaml": yaml.safe_dump(config, sort_keys=False)}}))
')
oc patch configmap launchpad-cluster-targets -n "$NAMESPACE" \
  --type=merge --patch "$cluster_patch" >/dev/null
oc set env deployment/backend -n "$NAMESPACE" --containers=backend \
  PUBLIC_ACCESS_ENABLED- \
  PUBLIC_LABS_SHARED_ORIGIN- \
  PUBLIC_ACCESS_PILOT_CLUSTER- >/dev/null
oc scale deployment/public-access-gateway --replicas=0 -n "$NAMESPACE" >/dev/null
oc scale deployment/cloudflare-tunnel --replicas=0 -n "$NAMESPACE" >/dev/null
oc rollout status deployment/backend -n "$NAMESPACE" --timeout=180s
printf 'Arena public pilot stopped and public ordering failed closed. Console and authentication operators were not modified.\n'
