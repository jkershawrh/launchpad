#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-cpu-serving-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-cpu-serving-seat.sh <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the expected execution cluster credential}"

actual_cluster="$(
  oc get namespace "$namespace" \
    -o jsonpath='{.metadata.labels.launchpad\.redhat\.com/cluster-id}'
)"
if [[ "$actual_cluster" != "$expected_cluster" ]]; then
  echo "refusing to mutate cluster '${actual_cluster}'; expected '${expected_cluster}'" >&2
  exit 2
fi

runtime_secret_json="$(
  oc exec -n "$namespace" deploy/showroom -c terminal -- \
    oc get secret launchpad-participant-runtime -n "$namespace" -o json
)"
if ! printf '%s' "$runtime_secret_json" | jq -e '
  (.data | keys | sort) == ["MAAS_API_KEY", "MAAS_API_URL", "MAAS_ENDPOINT", "MAAS_MODEL"]
  and all(.data[]; length > 0)
' >/dev/null; then
  echo "Participant terminal runtime contract is missing or incomplete" >&2
  exit 3
fi
endpoint="$(printf '%s' "$runtime_secret_json" | jq -r '.data.MAAS_ENDPOINT | @base64d')"
model="$(printf '%s' "$runtime_secret_json" | jq -r '.data.MAAS_MODEL | @base64d')"
api_key="$(printf '%s' "$runtime_secret_json" | jq -r '.data.MAAS_API_KEY | @base64d')"

jq -nc \
  --arg endpoint "${endpoint}/v1" \
  --arg model "$model" \
  --arg api_key "$api_key" \
  --arg image "image-registry.openshift-image-registry.svc:5000/partner-ai-launchpad/anythingllm-openshift@sha256:1eee2162bed8ab643133dd9420ea086566f7c778849e9ff3eddc71a6a6cd8f98" \
  '{
    apiVersion: "v1",
    kind: "List",
    items: [
      {
        apiVersion: "v1",
        kind: "Secret",
        metadata: {name: "anythingllm-config"},
        type: "Opaque",
        stringData: {
          LLM_PROVIDER: "generic-openai",
          GENERIC_OPEN_AI_BASE_PATH: $endpoint,
          GENERIC_OPEN_AI_MODEL_PREF: $model,
          GENERIC_OPEN_AI_API_KEY: $api_key,
          GENERIC_OPEN_AI_MAX_TOKENS: "512",
          EMBEDDING_ENGINE: "native",
          VECTOR_DB: "lancedb"
        }
      },
      {
        apiVersion: "apps/v1",
        kind: "Deployment",
        metadata: {name: "anythingllm"},
        spec: {
          replicas: 1,
          selector: {matchLabels: {app: "anythingllm"}},
          template: {
            metadata: {labels: {app: "anythingllm"}},
            spec: {
              containers: [
                {
                  name: "anythingllm",
                  image: $image,
                  ports: [{containerPort: 3001}],
                  envFrom: [{secretRef: {name: "anythingllm-config"}}],
                  env: [
                    {name: "STORAGE_DIR", value: "/tmp/anythingllm-storage"},
                    {name: "DISABLE_TELEMETRY", value: "true"}
                  ],
                  startupProbe: {
                    tcpSocket: {port: 3001},
                    failureThreshold: 60,
                    periodSeconds: 5
                  },
                  readinessProbe: {tcpSocket: {port: 3001}, periodSeconds: 5},
                  securityContext: {
                    allowPrivilegeEscalation: false,
                    capabilities: {drop: ["ALL"]}
                  },
                  resources: {
                    requests: {cpu: "1", memory: "1Gi"},
                    limits: {cpu: "2", memory: "2Gi"}
                  }
                }
              ]
            }
          }
        }
      },
      {
        apiVersion: "v1",
        kind: "Service",
        metadata: {name: "anythingllm"},
        spec: {
          selector: {app: "anythingllm"},
          ports: [{name: "3001", port: 3001, protocol: "TCP", targetPort: 3001}]
        }
      },
      {
        apiVersion: "route.openshift.io/v1",
        kind: "Route",
        metadata: {
          name: "rag",
          annotations: {"haproxy.router.openshift.io/timeout": "120s"}
        },
        spec: {
          to: {kind: "Service", name: "anythingllm", weight: 100},
          port: {targetPort: "3001"},
          tls: {termination: "edge", insecureEdgeTerminationPolicy: "Redirect"}
        }
      }
    ]
  }' \
  | oc exec -i -n "$namespace" deploy/showroom -c terminal -- \
      oc apply -n "$namespace" -f - >/dev/null

printf '%s\t%s\tdeployed\n' "$namespace" "$expected_cluster"
