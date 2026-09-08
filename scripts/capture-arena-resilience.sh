#!/usr/bin/env bash
set -euo pipefail

DEFAULT_KUBECONFIG="/Users/jkershaw/Documents/launchpad/.arena-kubeconfig"
ARENA_KUBECONFIG="${ARENA_KUBECONFIG:-$DEFAULT_KUBECONFIG}"
OUTPUT_DIR=""
SAMPLES=5
SINCE="$(python3 -c 'from datetime import datetime, timedelta, timezone; print((datetime.now(timezone.utc)-timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))')"
UNTIL="$(python3 -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))')"

usage() {
  printf '%s\n' \
    "Usage: $0 --output DIR [--since RFC3339] [--until RFC3339] [--samples N] [--kubeconfig PATH]" \
    "" \
    "Collect a read-only, credential-free Arena API, node, QoS, network, ingress," \
    "probe-wave, and kubelet/runtime diagnostic bundle."
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --output)
      OUTPUT_DIR="${2:?--output requires a directory}"
      shift 2
      ;;
    --since)
      SINCE="${2:?--since requires an RFC3339 timestamp}"
      shift 2
      ;;
    --until)
      UNTIL="${2:?--until requires an RFC3339 timestamp}"
      shift 2
      ;;
    --samples)
      SAMPLES="${2:?--samples requires a positive integer}"
      shift 2
      ;;
    --kubeconfig)
      ARENA_KUBECONFIG="${2:?--kubeconfig requires a path}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -z "$OUTPUT_DIR" ]; then
  printf '%s\n' "--output is required" >&2
  exit 2
fi
if [ ! -r "$ARENA_KUBECONFIG" ]; then
  printf 'Arena kubeconfig is not readable: %s\n' "$ARENA_KUBECONFIG" >&2
  exit 2
fi
case "$SAMPLES" in
  ''|*[!0-9]*|0)
    printf '%s\n' "--samples must be a positive integer" >&2
    exit 2
    ;;
esac

for dependency in oc jq python3 rg shasum; do
  if ! command -v "$dependency" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$dependency" >&2
    exit 2
  fi
done

OC=(oc "--kubeconfig=${ARENA_KUBECONFIG}")
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT
mkdir -p "$OUTPUT_DIR"

STARTED_AT="$(python3 -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))')"
jq -n \
  --arg schema "launchpad.redhat.com/arena-resilience-capture/v1" \
  --arg cluster_ref "arena" \
  --arg started_at "$STARTED_AT" \
  --arg since "$SINCE" \
  --arg until "$UNTIL" \
  --argjson samples "$SAMPLES" \
  '{
    schema: $schema,
    cluster_ref: $cluster_ref,
    started_at: $started_at,
    observation_window: {since: $since, until: $until},
    api_samples: $samples,
    mode: "read-only",
    contains_plaintext_credentials: false
  }' >"$OUTPUT_DIR/metadata.json"

printf '[]\n' >"$WORK_DIR/api-latency.json"
sample=1
while [ "$sample" -le "$SAMPLES" ]; do
  before="$(python3 -c 'import time; print(time.monotonic_ns())')"
  if "${OC[@]}" get --raw="/readyz" >"$WORK_DIR/readyz-${sample}.txt" 2>"$WORK_DIR/readyz-${sample}.err"; then
    status="ready"
  else
    status="unreachable"
  fi
  after="$(python3 -c 'import time; print(time.monotonic_ns())')"
  elapsed="$(python3 -c "print(round(max(0, (${after}-${before}))/1000000000, 6))")"
  jq \
    --argjson sample "$sample" \
    --arg status "$status" \
    --argjson seconds "$elapsed" \
    '. + [{sample: $sample, status: $status, seconds: $seconds}]' \
    "$WORK_DIR/api-latency.json" >"$WORK_DIR/api-latency.next.json"
  mv "$WORK_DIR/api-latency.next.json" "$WORK_DIR/api-latency.json"
  sample=$((sample + 1))
done
cp "$WORK_DIR/api-latency.json" "$OUTPUT_DIR/api-latency.json"

"${OC[@]}" get nodes -o json >"$WORK_DIR/nodes.raw.json"
jq '[.items[] | {
  name: .metadata.name,
  unschedulable: (.spec.unschedulable // false),
  conditions: [.status.conditions[] | {
    type, status, reason, lastHeartbeatTime, lastTransitionTime
  }],
  allocatable: {
    cpu: .status.allocatable.cpu,
    memory: .status.allocatable.memory,
    pods: .status.allocatable.pods
  },
  runtime: .status.nodeInfo.containerRuntimeVersion,
  kubelet: .status.nodeInfo.kubeletVersion
}]' "$WORK_DIR/nodes.raw.json" >"$OUTPUT_DIR/nodes.json"

"${OC[@]}" get pods -A -o json >"$WORK_DIR/pods.raw.json"
jq '[
  .items[]
  | select(.status.phase == "Running")
  | {node: .spec.nodeName, qos: .status.qosClass}
]
| sort_by(.node, .qos)
| group_by(.node, .qos)
| map({node: .[0].node, qos: .[0].qos, running_pods: length})' \
  "$WORK_DIR/pods.raw.json" >"$OUTPUT_DIR/qos-density.json"

jq '[
  .items[]
  | select(
      (.metadata.namespace == "openshift-ovn-kubernetes") or
      (.metadata.namespace == "openshift-multus") or
      (.metadata.namespace == "openshift-dns") or
      (.metadata.namespace == "openshift-ingress") or
      (.metadata.namespace == "partner-ai-launchpad") or
      (.metadata.namespace == "fleet-llm-d") or
      (.metadata.namespace | startswith("launchpad-"))
    )
  | {
      namespace: .metadata.namespace,
      name: .metadata.name,
      node: .spec.nodeName,
      phase: .status.phase,
      qos: .status.qosClass,
      pod_ip: .status.podIP,
      containers: [.status.containerStatuses[]? | {
        name, ready, restartCount,
        last_termination: (.lastState.terminated.finishedAt // null)
      }]
    }
]' "$WORK_DIR/pods.raw.json" >"$OUTPUT_DIR/critical-pods.json"

"${OC[@]}" get events -A -o json >"$WORK_DIR/events.raw.json"
jq \
  --arg since "$SINCE" \
  --arg until "$UNTIL" \
  '[
    .items[]
    | (.eventTime // .lastTimestamp // .metadata.creationTimestamp) as $timestamp
    | select($timestamp >= $since and $timestamp <= $until)
    | select(
        (.reason == "Unhealthy") or
        (.reason == "ProbeError") or
        ((.message // .note // "") | test("context deadline exceeded|i/o timeout|PLEG is not healthy"; "i"))
      )
    | ((.message // .note // "") | tostring) as $message
    | {
        timestamp: $timestamp,
        minute: ($timestamp[0:16] + "Z"),
        namespace: .metadata.namespace,
        reason: .reason,
        object_kind: (.involvedObject.kind // .regarding.kind // null),
        object_name: (.involvedObject.name // .regarding.name // null),
        node_hint: (
          if ($message | test("10\\.130\\.")) then "gnr2.fm2aihpcsed.com"
          elif ($message | test("10\\.129\\.")) then "rhgnr1"
          else "unknown"
          end
        ),
        occurrence_count: (.count // 1),
        signature: (
          if ($message | test("PLEG is not healthy"; "i")) then "pleg-not-healthy"
          elif ($message | test("context deadline exceeded"; "i")) then "context-deadline"
          elif ($message | test("i/o timeout"; "i")) then "io-timeout"
          else "probe-failure"
          end
        )
      }
  ]
  | sort_by(.minute, .node_hint, .namespace)
  | group_by(.minute, .node_hint)
  | map({
      minute: .[0].minute,
      node_hint: .[0].node_hint,
      event_records: length,
      namespaces: ([.[].namespace] | unique),
      signatures: ([.[].signature] | group_by(.) | map({signature: .[0], records: length}))
    })' "$WORK_DIR/events.raw.json" >"$OUTPUT_DIR/probe-waves.json"

"${OC[@]}" get kubeletconfig -o json >"$WORK_DIR/kubelet-config.raw.json"
jq '[.items[] | {
  name: .metadata.name,
  selector: .spec.machineConfigPoolSelector,
  cpuManagerPolicy: .spec.kubeletConfig.cpuManagerPolicy,
  cpuManagerPolicyOptions: .spec.kubeletConfig.cpuManagerPolicyOptions,
  reservedSystemCPUs: .spec.kubeletConfig.reservedSystemCPUs,
  topologyManagerPolicy: .spec.kubeletConfig.topologyManagerPolicy,
  topologyManagerPolicyOptions: .spec.kubeletConfig.topologyManagerPolicyOptions
}]' "$WORK_DIR/kubelet-config.raw.json" >"$OUTPUT_DIR/kubelet-config.json"

LOG_SINCE="$(printf '%s' "$SINCE" | sed 's/T/ /; s/Z$//')"
LOG_UNTIL="$(printf '%s' "$UNTIL" | sed 's/T/ /; s/Z$//')"
printf '[]\n' >"$WORK_DIR/node-runtime-warnings.json"
for node in gnr2.fm2aihpcsed.com rhgnr1; do
  for unit in kubelet crio; do
    log_file="$WORK_DIR/${node}-${unit}.log"
    if ! "${OC[@]}" adm node-logs "$node" -u "$unit" \
      --since="$LOG_SINCE" --until="$LOG_UNTIL" --tail=10000 \
      >"$log_file" 2>/dev/null; then
      : >"$log_file"
    fi
    {
      rg -i \
        'context deadline exceeded|i/o timeout|PLEG is not healthy|Container runtime status|probe.*failed|Failed to create pod sandbox|container status.*not found|image garbage collection failed' \
        "$log_file" 2>/dev/null || true
    } | jq -R -s --arg node "$node" --arg unit "$unit" '
        def count_matching($expression):
          map(select(test($expression; "i"))) | length;
        split("\n")
        | map(select(length > 0)) as $matches
        | {
            node: $node,
            unit: $unit,
            matching_lines: ($matches | length),
            signatures: {
              context_deadline: ($matches | count_matching("context deadline exceeded")),
              io_timeout: ($matches | count_matching("i/o timeout")),
              pleg_unhealthy: ($matches | count_matching("PLEG is not healthy")),
              runtime_status: ($matches | count_matching("Container runtime status|container status.*not found")),
              probe_failure: ($matches | count_matching("probe.*failed")),
              sandbox_failure: ($matches | count_matching("Failed to create pod sandbox")),
              image_gc_failure: ($matches | count_matching("image garbage collection failed"))
            }
          }
      ' >"$WORK_DIR/node-unit.json"
    jq --slurpfile entry "$WORK_DIR/node-unit.json" '. + $entry' \
      "$WORK_DIR/node-runtime-warnings.json" >"$WORK_DIR/node-runtime-warnings.next.json"
    mv "$WORK_DIR/node-runtime-warnings.next.json" "$WORK_DIR/node-runtime-warnings.json"
  done
done
cp "$WORK_DIR/node-runtime-warnings.json" "$OUTPUT_DIR/node-runtime-warnings.json"

(
  cd "$OUTPUT_DIR"
  shasum -a 256 \
    metadata.json api-latency.json nodes.json qos-density.json critical-pods.json \
    probe-waves.json kubelet-config.json node-runtime-warnings.json \
    >manifest.sha256
)

printf 'Arena resilience bundle written to %s\n' "$OUTPUT_DIR"
