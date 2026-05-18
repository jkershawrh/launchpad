# OpenShift Manifests - CPU Inference Path

Kubernetes/OpenShift manifests for deploying vLLM CPU inference on Intel Xeon6 workers.

## Structure

```
cpu-inference/
├── namespace.yaml              # Namespace definition
├── serving-runtime.yaml        # KServe ServingRuntime for vLLM CPU
├── inference-service.yaml      # KServe InferenceService example
├── network-policy.yaml         # NetworkPolicy for isolation
├── kustomization.yaml          # Kustomize configuration
└── README.md                   # This file
```

## Prerequisites

- OpenShift 4.12+ or Kubernetes 1.24+
- KServe 0.11+ installed
- OpenShift AI operator (for Red Hat OpenShift)
- `oc` or `kubectl` CLI
- `kustomize` CLI (optional, for customization)

## Quick Deploy

### Using Kustomize (Recommended)

```bash
# Preview manifests
kustomize build .

# Apply to cluster
kustomize build . | oc apply -f -

# Or use kubectl kustomize
kubectl apply -k .
```

### Using oc/kubectl Directly

```bash
# Apply each manifest
oc apply -f namespace.yaml
oc apply -f serving-runtime.yaml
oc apply -f inference-service.yaml
oc apply -f network-policy.yaml
```

## Configuration

### Before Deployment

**Update image reference** in `serving-runtime.yaml`:

```yaml
image: "[TBD: quay.io/organization/vllm-cpu@sha256:digest]"
```

Replace with actual image:
```yaml
image: "quay.io/your-org/vllm-cpu@sha256:actual-digest"
```

**Update node selector** (after cluster discovery):

Uncomment and update in `serving-runtime.yaml`:
```yaml
nodeSelector:
  intel.com/xeon6: "true"
  node-role.kubernetes.io/worker: ""
```

### Resource Limits

Default resources in `serving-runtime.yaml`:
- **Requests**: 2 CPU, 4Gi memory
- **Limits**: 4 CPU, 8Gi memory

Adjust based on:
- Model size
- Expected throughput
- Cluster capacity

### Model Configuration

Specify model in `inference-service.yaml`:

```yaml
env:
  - name: MODEL_NAME
    value: "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
```

Supported models (must be approved):
- TinyLlama/TinyLlama-1.1B-Chat-v1.0 (1.1B)
- microsoft/phi-2 (2.7B)
- microsoft/Phi-3-mini-4k-instruct (3.8B)

## Testing

### Check Deployment Status

```bash
# Check namespace
oc get ns intel-rh-cpu-inference

# Check ServingRuntime
oc get servingruntime -n intel-rh-cpu-inference

# Check InferenceService
oc get inferenceservice -n intel-rh-cpu-inference

# Check pods
oc get pods -n intel-rh-cpu-inference

# Get logs
oc logs -n intel-rh-cpu-inference -l app.kubernetes.io/name=cpu-inference-example
```

### Test Inference

```bash
# Get the inference service URL
ISVC_URL=$(oc get inferenceservice cpu-inference-example \
  -n intel-rh-cpu-inference \
  -o jsonpath='{.status.url}')

echo "Inference URL: $ISVC_URL"

# Send test request
curl -X POST $ISVC_URL/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    "prompt": "The capital of France is",
    "max_tokens": 10
  }'
```

## Scaling

### Manual Scaling

Edit `inference-service.yaml`:
```yaml
spec:
  predictor:
    minReplicas: 1
    maxReplicas: 5
```

### Autoscaling

KServe autoscales based on:
- Request concurrency (default)
- Custom metrics (optional)

Configure in `inference-service.yaml`:
```yaml
scaleTarget: 10  # Target concurrent requests per pod
scaleMetric: concurrency
```

## Security

### Network Isolation

NetworkPolicy (`network-policy.yaml`) restricts:
- **Ingress**: Only from ingress controller, same namespace, monitoring
- **Egress**: DNS, HTTPS (for model downloads), internal services

### Pod Security

ServingRuntime enforces:
- Non-root user (UID 1001)
- No privilege escalation
- Capabilities dropped (ALL)
- SecComp profile (RuntimeDefault)

### RBAC

Create ServiceAccount and RoleBinding:
```bash
oc create sa cpu-inference-sa -n intel-rh-cpu-inference
oc adm policy add-role-to-user view \
  system:serviceaccount:intel-rh-cpu-inference:cpu-inference-sa
```

## Monitoring

### Metrics

InferenceService exposes metrics on `:8080/metrics`:
- Request count
- Latency (p50, p95, p99)
- Error rate
- Model loading time

### Logging

View logs:
```bash
# All pods in namespace
oc logs -n intel-rh-cpu-inference --tail=100 -l serving.kserve.io/inferenceservice=cpu-inference-example

# Specific pod
oc logs -n intel-rh-cpu-inference <pod-name>

# Follow logs
oc logs -n intel-rh-cpu-inference <pod-name> -f
```

## Troubleshooting

### Pod Not Starting

```bash
# Check events
oc get events -n intel-rh-cpu-inference --sort-by='.lastTimestamp'

# Check pod status
oc describe pod -n intel-rh-cpu-inference <pod-name>

# Check resource constraints
oc get resourcequota -n intel-rh-cpu-inference
```

### Model Download Failing

Check network policy allows HTTPS egress:
```bash
oc describe networkpolicy -n intel-rh-cpu-inference
```

Set HuggingFace token (for private models):
```yaml
env:
  - name: HF_TOKEN
    valueFrom:
      secretKeyRef:
        name: huggingface-secret
        key: token
```

### Inference Errors

Check logs for details:
```bash
oc logs -n intel-rh-cpu-inference -l app.kubernetes.io/name=cpu-inference-example --tail=50
```

Common issues:
- Out of memory → increase resource limits
- Model not found → check MODEL_NAME env var
- Timeout → increase readiness probe timeout

## Cleanup

```bash
# Delete everything
kustomize build . | oc delete -f -

# Or delete namespace (removes all resources)
oc delete namespace intel-rh-cpu-inference
```

## Integration with OpenShift AI

If using Red Hat OpenShift AI:

1. Ensure OpenShift AI operator is installed
2. ServingRuntime will be automatically discovered
3. Use Data Science Projects UI to deploy

## Customization

### Environment-Specific Overlays

Create overlays for different environments:

```
cpu-inference/
├── base/              # Base manifests (current files)
└── overlays/
    ├── dev/
    │   └── kustomization.yaml
    ├── staging/
    │   └── kustomization.yaml
    └── prod/
        ├── kustomization.yaml
        └── patches/
            └── prod-resources.yaml
```

Deploy with overlay:
```bash
kustomize build overlays/prod | oc apply -f -
```

## Next Steps

1. Update [TBD] placeholders with actual values
2. Test deployment on Rackspace cluster
3. Capture image digests from successful deployment
4. Update golden paths documentation
5. Create partner quickstart guide

---

**Platform**: Intel Xeon6 CPU Inference  
**Runtime**: vLLM (transformers-based)  
**Orchestration**: KServe on OpenShift
