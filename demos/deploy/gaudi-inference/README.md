# OpenShift Manifests - Gaudi GPU Inference Path

Kubernetes/OpenShift manifests for deploying vLLM GPU inference on Intel Gaudi accelerators.

## Structure

```
gaudi-inference/
├── namespace.yaml              # Namespace definition
├── serving-runtime.yaml        # KServe ServingRuntime for vLLM Gaudi
├── inference-service.yaml      # KServe InferenceService example
├── network-policy.yaml         # NetworkPolicy for isolation
├── kustomization.yaml          # Kustomize configuration
└── README.md                   # This file
```

## Prerequisites

- OpenShift 4.12+ or Kubernetes 1.24+
- KServe 0.11+ installed
- OpenShift AI operator (for Red Hat OpenShift)
- **Intel Gaudi GPU nodes** with Habana device plugin installed
- `oc` or `kubectl` CLI
- `kustomize` CLI (optional, for customization)

### Gaudi-Specific Requirements

- Habana device plugin running on Gaudi nodes
- Node labels identifying Gaudi-enabled nodes
- Available `habana.ai/gaudi` resources
- Gaudi drivers installed on nodes

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
image: "[TBD: quay.io/organization/vllm-gaudi@sha256:digest]"
```

Replace with actual Gaudi image:
```yaml
image: "quay.io/your-org/vllm-gaudi@sha256:actual-digest"
```

**Update node selector** (after cluster discovery):

Uncomment and update in `serving-runtime.yaml`:
```yaml
nodeSelector:
  intel.com/gaudi: "true"
  node-role.kubernetes.io/worker: ""
  accelerator: gaudi
```

**Verify Gaudi resource availability**:

```bash
# Check Gaudi device plugin is running
oc get pods -n kube-system | grep habana

# Check node resources
oc describe node <gaudi-node-name> | grep habana.ai/gaudi
```

### Resource Limits

Default resources in `serving-runtime.yaml`:
- **CPU Requests**: 4 cores
- **CPU Limits**: 8 cores
- **Memory Requests**: 16Gi
- **Memory Limits**: 32Gi
- **Gaudi GPU**: 1 device (`habana.ai/gaudi: "1"`)

Adjust based on:
- Model size (larger models need more memory)
- Expected throughput
- Number of available Gaudi devices

### Model Configuration

Specify model in `inference-service.yaml`:

```yaml
env:
  - name: MODEL_NAME
    value: "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
```

Supported models (must be approved):
- TinyLlama/TinyLlama-1.1B-Chat-v1.0 (1.1B) - for testing
- microsoft/phi-2 (2.7B) - good for Gaudi
- microsoft/Phi-3-mini-4k-instruct (3.8B)
- meta-llama/Llama-2-7b-chat-hf (7B) - requires approval

**Note**: Gaudi GPUs are designed for larger models. For small models like TinyLlama, consider using the CPU inference path instead.

## Testing

### Check Deployment Status

```bash
# Check namespace
oc get ns intel-rh-gaudi-inference

# Check ServingRuntime
oc get servingruntime -n intel-rh-gaudi-inference

# Check InferenceService
oc get inferenceservice -n intel-rh-gaudi-inference

# Check pods
oc get pods -n intel-rh-gaudi-inference

# Verify Gaudi assignment
oc describe pod -n intel-rh-gaudi-inference <pod-name> | grep -A 5 "Limits:"
```

Expected output should show:
```
Limits:
  cpu:                8
  habana.ai/gaudi:    1
  memory:             32Gi
```

### Get Logs

```bash
# Get logs
oc logs -n intel-rh-gaudi-inference -l app.kubernetes.io/name=gaudi-inference-example

# Check for Gaudi initialization
oc logs -n intel-rh-gaudi-inference <pod-name> | grep -i gaudi
oc logs -n intel-rh-gaudi-inference <pod-name> | grep -i habana
```

### Test Inference

```bash
# Get the inference service URL
ISVC_URL=$(oc get inferenceservice gaudi-inference-example \
  -n intel-rh-gaudi-inference \
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
    maxReplicas: 3  # Limited by available Gaudi devices
```

**Important**: Each replica requires one Gaudi GPU. Ensure you have sufficient Gaudi devices available.

### Autoscaling

KServe autoscales based on request concurrency:

```yaml
containerConcurrency: 5  # Gaudi can handle more than CPU
scaleTarget: 10
scaleMetric: concurrency
```

**Gaudi Consideration**: Gaudi GPUs are expensive. Consider keeping minReplicas at 1 or higher to avoid cold start latency.

## Performance Optimization

### Gaudi-Specific Settings

In `serving-runtime.yaml`:

```yaml
env:
  - name: HABANA_VISIBLE_DEVICES
    value: "all"  # Use all available Gaudi devices
  - name: HABANA_LOGS
    value: /opt/app-root/src/logs/habana
```

### Concurrent Requests

Gaudi GPUs can handle multiple concurrent requests efficiently:

```yaml
containerConcurrency: 5  # Higher than CPU (typically 1)
```

### Model Loading

Larger models benefit more from Gaudi acceleration:
- 7B+ models: Significant speedup vs CPU
- 2-3B models: Moderate speedup
- <2B models: Consider CPU path instead

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

**Note**: Gaudi device access does not require privileged containers.

### RBAC

Create ServiceAccount and RoleBinding:
```bash
oc create sa gaudi-inference-sa -n intel-rh-gaudi-inference
oc adm policy add-role-to-user view \
  system:serviceaccount:intel-rh-gaudi-inference:gaudi-inference-sa
```

## Monitoring

### Gaudi-Specific Metrics

InferenceService exposes metrics on `:8080/metrics`:
- Standard metrics: request count, latency, error rate
- **Gaudi metrics**: HPU utilization, memory usage (if exposed)

### Check Gaudi Utilization

```bash
# SSH to Gaudi node (if permitted)
hl-smi  # Habana System Management Interface

# Or check via pod
oc exec -n intel-rh-gaudi-inference <pod-name> -- env | grep HABANA
```

### Logging

View logs:
```bash
# All pods in namespace
oc logs -n intel-rh-gaudi-inference --tail=100 -l serving.kserve.io/inferenceservice=gaudi-inference-example

# Follow logs
oc logs -n intel-rh-gaudi-inference <pod-name> -f

# Check for Gaudi initialization
oc logs -n intel-rh-gaudi-inference <pod-name> | grep -i "gaudi\|habana\|hpu"
```

## Troubleshooting

### Pod Not Starting

```bash
# Check events
oc get events -n intel-rh-gaudi-inference --sort-by='.lastTimestamp'

# Check pod status
oc describe pod -n intel-rh-gaudi-inference <pod-name>

# Common issues:
# - No Gaudi devices available
# - Gaudi device plugin not running
# - Node selector mismatch
```

### No Gaudi Devices Available

```bash
# Check node resources
oc describe nodes | grep -A 10 "Allocatable:"

# Should show:
#   habana.ai/gaudi: 8  (or number of Gaudi devices per node)

# If not present:
# 1. Verify Gaudi device plugin is running
# 2. Check node labels
# 3. Verify Gaudi drivers installed
```

### Gaudi Device Not Detected

Check logs for device detection:
```bash
oc logs -n intel-rh-gaudi-inference <pod-name> | grep -i "device\|gaudi"

# If "No Gaudi devices found":
# 1. Verify habana.ai/gaudi resource requested
# 2. Check device plugin logs
# 3. Verify node has Gaudi hardware
```

### Model Download Failing

Same as CPU path - check network policy allows HTTPS egress.

For private models, add HuggingFace token:
```yaml
env:
  - name: HF_TOKEN
    valueFrom:
      secretKeyRef:
        name: huggingface-secret
        key: token
```

### Inference Slower Than Expected

Check:
1. **Gaudi actually in use**: Look for HPU logs
2. **Mock mode disabled**: Check `HABANA_USE_MOCK` not set to "true"
3. **Model size appropriate**: Small models may not benefit from Gaudi
4. **Concurrent requests**: Gaudi excels with batching

```bash
# Check if running in mock mode
oc logs -n intel-rh-gaudi-inference <pod-name> | grep HABANA_USE_MOCK
```

## Cleanup

```bash
# Delete everything
kustomize build . | oc delete -f -

# Or delete namespace (removes all resources)
oc delete namespace intel-rh-gaudi-inference
```

## CPU vs Gaudi: When to Use Which

### Use **CPU Inference** when:
- Model is small (<2B parameters)
- Latency is not critical (>1s acceptable)
- Cost efficiency is priority
- Testing/development
- Low request volume

### Use **Gaudi Inference** when:
- Model is large (7B+ parameters)
- Low latency required (<100ms TTFT)
- High throughput needed
- Production workloads
- Batch processing

## Integration with OpenShift AI

If using Red Hat OpenShift AI:

1. Ensure OpenShift AI operator is installed
2. ServingRuntime will be automatically discovered
3. Gaudi devices must be available via device plugin
4. Use Data Science Projects UI to deploy

## Customization

### Environment-Specific Overlays

Create overlays for different environments:

```
gaudi-inference/
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
2. Test deployment on Rackspace Gaudi cluster
3. Capture image digests from successful deployment
4. Document Gaudi-specific node labels
5. Benchmark performance vs CPU path
6. Create partner quickstart guide

## Performance Expectations

**Gaudi vs CPU** (approximate, model-dependent):

| Metric | CPU (Xeon6) | Gaudi GPU |
|--------|-------------|-----------|
| TTFT (7B model) | ~10-30s | <2s |
| Throughput | 5-10 tok/s | 100+ tok/s |
| Concurrency | 1-2 | 5-10 |
| Model Size Limit | ~7B | 70B+ |

**Note**: Actual performance depends on model architecture, batch size, and workload characteristics.

---

**Platform**: Intel Gaudi GPU Inference  
**Runtime**: vLLM (Gaudi-optimized)  
**Orchestration**: KServe on OpenShift  
**Resource**: `habana.ai/gaudi`
