# Gaudi GPU Inference Hello World

**Deploy your first AI inference service on Intel Gaudi GPUs in under 15 minutes.**

This quickstart demonstrates deploying a lightweight LLM inference service using vLLM on OpenShift with Intel Gaudi GPU acceleration. You'll deploy TinyLlama (1.1B parameters) and test GPU-accelerated text generation via REST API.

## What You'll Build

- **InferenceService**: KServe-managed service running on Gaudi GPU
- **GPU-accelerated runtime**: vLLM inference on Intel Gaudi accelerators
- **REST API**: OpenAI-compatible completions endpoint
- **Autoscaling**: 1-3 pods (limited by available Gaudi devices)

**Estimated time**: 15 minutes  
**Cost**: Higher than CPU (Gaudi GPUs are premium resources)

## CPU vs Gaudi: When to Use Which

### Use **CPU Inference** ([cpu-hello-world](../cpu-hello-world/)) when:
- Model is small (<2B parameters)
- Latency tolerance > 1 second
- **Cost efficiency is priority**
- Development and testing
- Low request volume

**Performance**: TTFT ~10-30s, Throughput ~5-10 tokens/sec

### Use **Gaudi Inference** (this guide) when:
- Model is large (7B+ parameters recommended)
- **Low latency required** (< 100ms TTFT)
- High throughput needed (100+ tokens/sec)
- Production workloads with scale
- Batch processing

**Performance**: TTFT <2s, Throughput 100+ tokens/sec

**For this demo**: We use TinyLlama (1.1B) to validate Gaudi setup, but in production, use Gaudi for larger models where the GPU acceleration provides significant value.

## Prerequisites

Before starting, ensure you have:

### Required Tools

- **oc** - OpenShift CLI (version 4.12+)  
  Download: https://mirror.openshift.com/pub/openshift-v4/clients/oc/latest/
- **kubectl** - Kubernetes CLI (alternative to oc)  
  Download: https://kubernetes.io/docs/tasks/tools/
- **kustomize** - Kubernetes manifest customization tool  
  Download: https://kubectl.docs.kubernetes.io/installation/kustomize/

### Cluster Requirements

- OpenShift 4.12+ or Kubernetes 1.24+
- Cluster admin or sufficient permissions to create namespaces
- KServe 0.11+ installed (or OpenShift AI operator)
- **Intel Gaudi GPU nodes** with Habana device plugin

### Gaudi-Specific Prerequisites

**Critical**: This quickstart requires Intel Gaudi GPU nodes.

Verify Gaudi availability:

```bash
# Check for Gaudi device plugin
oc get pods -n kube-system | grep habana

# Check node resources
oc get nodes -o json | jq '.items[].status.allocatable | select(.["habana.ai/gaudi"])'
```

Expected output:
```json
{
  "cpu": "96",
  "habana.ai/gaudi": "8",
  "memory": "528Gi"
}
```

If no Gaudi resources found, contact your cluster administrator or use the [CPU inference path](../cpu-hello-world/) instead.

### Login to Cluster

```bash
# Login to OpenShift cluster
oc login --server=https://your-cluster-api:6443 --token=your-token

# Verify connection
oc whoami
oc version
```

## Quick Deploy

1. **Navigate to the manifests directory**

   ```bash
   cd /path/to/project/deploy/gaudi-inference
   ```

2. **Review configuration** (optional)

   The default configuration uses:
   - **Model**: TinyLlama/TinyLlama-1.1B-Chat-v1.0 (1.1B params)
   - **Resources**: 4-8 CPU, 16-32Gi memory, **1 Gaudi GPU**
   - **Replicas**: 1-3 (autoscaling, limited by available Gaudi devices)

   To use a different model, edit `inference-service.yaml`:

   ```yaml
   env:
     - name: MODEL_NAME
       value: "TinyLlama/TinyLlama-1.1B-Chat-v1.0"  # Change this
   ```

   Recommended models for Gaudi:
   - microsoft/phi-2 (2.7B) - Good for Gaudi
   - microsoft/Phi-3-mini-4k-instruct (3.8B) - Better
   - meta-llama/Llama-2-7b-chat-hf (7B) - Requires approval, ideal for Gaudi

3. **Deploy with Kustomize**

   ```bash
   # Preview what will be deployed
   kustomize build .

   # Deploy to cluster
   kustomize build . | oc apply -f -
   ```

   Expected output:
   ```
   namespace/intel-rh-gaudi-inference created
   servingruntime.serving.kserve.io/vllm-gaudi-runtime created
   inferenceservice.serving.kserve.io/gaudi-inference-example created
   networkpolicy.networking.k8s.io/gaudi-inference-netpol created
   ```

   **Alternative** (using kubectl/oc directly):

   ```bash
   kubectl apply -k .
   # or
   oc apply -k .
   ```

4. **Monitor deployment progress**

   Watch the deployment:

   ```bash
   # Check InferenceService status
   oc get inferenceservice gaudi-inference-example -n intel-rh-gaudi-inference -w

   # Check pods
   oc get pods -n intel-rh-gaudi-inference

   # Verify Gaudi GPU assignment
   oc describe pod -n intel-rh-gaudi-inference <pod-name> | grep -A 5 "Limits:"
   ```

   **Expected Gaudi assignment**:
   ```
   Limits:
     cpu:                8
     habana.ai/gaudi:    1
     memory:             32Gi
   ```

   **Deployment is ready when**:
   ```
   NAME                       READY   URL
   gaudi-inference-example    True    http://gaudi-inference-example-intel-rh-gaudi-inference.apps.cluster.com
   ```

   This may take 3-5 minutes while the model downloads (~2GB) and loads into Gaudi GPU memory.

   View logs to see Gaudi initialization:

   ```bash
   oc logs -n intel-rh-gaudi-inference -l serving.kserve.io/inferenceservice=gaudi-inference-example -f | grep -i "gaudi\|habana\|hpu"
   ```

## Test the Deployment

5. **Get the inference URL**

   ```bash
   # Retrieve the inference service URL
   ISVC_URL=$(oc get inferenceservice gaudi-inference-example \
     -n intel-rh-gaudi-inference \
     -o jsonpath='{.status.url}')

   echo "Inference URL: $ISVC_URL"
   ```

   Expected output:
   ```
   Inference URL: http://gaudi-inference-example-intel-rh-gaudi-inference.apps.your-cluster.com
   ```

6. **Send a test request**

   ```bash
   # Test the completions endpoint
   curl -X POST $ISVC_URL/v1/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
       "prompt": "The capital of France is",
       "max_tokens": 10
     }'
   ```

   Expected output:
   ```json
   {
     "id": "cmpl-...",
     "object": "text_completion",
     "created": 1234567890,
     "model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
     "choices": [
       {
         "text": " Paris. The city is known for",
         "index": 0,
         "finish_reason": "length"
       }
     ],
     "usage": {
       "prompt_tokens": 6,
       "completion_tokens": 10,
       "total_tokens": 16
     }
   }
   ```

7. **Measure performance (Gaudi advantage)**

   Time the request to see Gaudi acceleration:

   ```bash
   # Time the request
   time curl -X POST $ISVC_URL/v1/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
       "prompt": "Once upon a time in a land far away",
       "max_tokens": 50
     }'
   ```

   **Expected performance**:
   - Time to first token: < 2s (Gaudi)
   - Total time for 50 tokens: 2-5s (Gaudi)

   **Compare to CPU** (from cpu-hello-world):
   - Time to first token: 10-30s (CPU)
   - Total time for 50 tokens: 15-40s (CPU)

   **Gaudi speedup**: 5-10x faster for inference

## Verify Gaudi GPU Usage

### Check Resource Allocation

```bash
# Describe pod to see Gaudi allocation
oc describe pod -n intel-rh-gaudi-inference <pod-name> | grep habana.ai/gaudi
```

Expected: `habana.ai/gaudi: 1`

### Check Gaudi Device Detection

```bash
# View logs for Gaudi initialization
oc logs -n intel-rh-gaudi-inference <pod-name> | grep -i "gaudi\|habana"
```

Should see logs indicating Gaudi device detection and initialization.

### Check Node Assignment

```bash
# Verify pod is on a Gaudi-enabled node
oc get pod -n intel-rh-gaudi-inference <pod-name> -o jsonpath='{.spec.nodeName}'

# Check that node has Gaudi resources
oc describe node <node-name> | grep habana.ai/gaudi
```

## Troubleshooting

### Pod Stuck in Pending

**Symptom**: Pod shows "Pending" status for several minutes

**Common causes**:

1. **No Gaudi GPUs available**

   ```bash
   # Check cluster-wide Gaudi availability
   oc get nodes -o json | jq '.items[] | select(.status.allocatable["habana.ai/gaudi"] != null) | {name: .metadata.name, gaudi: .status.allocatable["habana.ai/gaudi"]}'
   ```

   **Solution**: Wait for Gaudi GPU to become available, or reduce replicas

2. **Node selector mismatch**

   Check node labels:
   ```bash
   oc get nodes --show-labels | grep gaudi
   ```

   Update `serving-runtime.yaml` nodeSelector to match actual labels

3. **Resource quota exceeded**

   ```bash
   oc describe resourcequota -n intel-rh-gaudi-inference
   ```

### Pod Running but Inference Slow

**Symptom**: Performance similar to CPU, no Gaudi acceleration

**Diagnosis**:

```bash
# Check if running in mock mode
oc logs -n intel-rh-gaudi-inference <pod-name> | grep HABANA_USE_MOCK

# Should show: HABANA_USE_MOCK=false (or not present)
# If shows: HABANA_USE_MOCK=true - this is wrong for production
```

**Solution**: Verify `serving-runtime.yaml` has `HABANA_USE_MOCK: "false"` or remove the variable entirely

### Gaudi Device Not Detected

**Symptom**: Logs show "No Gaudi devices found" or "Using CPU fallback"

**Diagnosis**:

```bash
# Check habana.ai/gaudi resource in pod spec
oc get pod -n intel-rh-gaudi-inference <pod-name> -o yaml | grep -A 5 "limits:"

# Should show:
#   limits:
#     habana.ai/gaudi: "1"
```

**Solution**: Ensure `inference-service.yaml` requests `habana.ai/gaudi: "1"`

### Model Too Large for Single Gaudi

**Symptom**: Out of memory errors

**Solution**: 
1. Use a smaller model
2. Request multiple Gaudi devices (if available)
3. Use tensor parallelism (advanced configuration)

## Cleanup

```bash
# Delete everything
kustomize build . | oc delete -f -

# Or delete the entire namespace
oc delete namespace intel-rh-gaudi-inference
```

**Verify cleanup:**
```bash
oc get ns intel-rh-gaudi-inference
# Should return: Error from server (NotFound)
```

## Next Steps

### Use a Larger Model (Leverage Gaudi)

TinyLlama is too small to show Gaudi's full potential. Try larger models:

Update `inference-service.yaml`:

```yaml
env:
  - name: MODEL_NAME
    value: "microsoft/phi-2"  # 2.7B - good for Gaudi

resources:
  requests:
    cpu: "8"
    memory: "32Gi"
    habana.ai/gaudi: "1"
  limits:
    cpu: "16"
    memory: "64Gi"
    habana.ai/gaudi: "1"
```

Redeploy:
```bash
kustomize build . | oc apply -f -
```

### Compare Performance: CPU vs Gaudi

Run the same workload on both paths and measure:

**CPU Path**:
```bash
cd ../cpu-hello-world
./deploy.sh
./test.sh --benchmark
```

**Gaudi Path** (this quickstart):
```bash
cd ../gaudi-hello-world
./deploy.sh
./test.sh --benchmark
```

Document the speedup for your specific use case.

### Scale Based on Load

For production workloads:

```yaml
spec:
  predictor:
    minReplicas: 2  # Keep warm (avoid cold starts)
    maxReplicas: 5  # Scale based on available Gaudi GPUs
    containerConcurrency: 10  # Gaudi handles more concurrent requests
```

### Integration with Applications

Use the OpenAI-compatible API from your application:

```python
import openai

client = openai.OpenAI(
    base_url="http://gaudi-inference-example-intel-rh-gaudi-inference.apps.cluster.com/v1",
    api_key="not-required"  # No auth in this example
)

response = client.completions.create(
    model="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    prompt="Hello world",
    max_tokens=50
)
print(response.choices[0].text)
```

## Reference Files

All manifests are in `../../deploy/gaudi-inference/`:

- `namespace.yaml` - Namespace definition
- `serving-runtime.yaml` - vLLM Gaudi runtime with `habana.ai/gaudi` resources
- `inference-service.yaml` - InferenceService example
- `network-policy.yaml` - Network isolation rules
- `kustomization.yaml` - Kustomize build configuration

## Performance Comparison

| Metric | CPU (Xeon6) | Gaudi GPU | Speedup |
|--------|-------------|-----------|---------|
| TTFT (1B model) | 10-30s | <2s | **5-15x** |
| Throughput (1B) | 5-10 tok/s | 100+ tok/s | **10-20x** |
| TTFT (7B model) | 60-120s | <2s | **30-60x** |
| Throughput (7B) | 1-3 tok/s | 100+ tok/s | **30-100x** |
| Max Model Size | ~7B | 70B+ | **10x+** |
| Cost per Token | Low | Higher | - |

**Recommendation**: Use Gaudi for models ≥7B where the performance gain justifies the cost.

## Support

- **Documentation**: See `deploy/gaudi-inference/README.md` for detailed configuration
- **CPU Alternative**: If no Gaudi available, use `../cpu-hello-world/` instead
- **Issues**: Report bugs to your platform team
- **Model requests**: Submit approved model requests through official channels

---

**Platform**: Intel Gaudi GPU Inference  
**Runtime**: vLLM (Gaudi-optimized)  
**Orchestration**: KServe on OpenShift  
**Resource Type**: `habana.ai/gaudi`  
**Time to Deploy**: ~15 minutes  
**Best For**: Large models (7B+), low latency, high throughput
