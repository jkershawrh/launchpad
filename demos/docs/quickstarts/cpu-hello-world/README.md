# CPU Inference Hello World

**Deploy your first AI inference service on Intel Xeon6 CPUs in under 10 minutes.**

This quickstart demonstrates deploying a lightweight LLM inference service using vLLM on OpenShift with CPU-only nodes. You'll deploy TinyLlama (1.1B parameters) and test text generation via REST API.

## What You'll Build

- **InferenceService**: KServe-managed service running TinyLlama
- **CPU-optimized runtime**: vLLM inference on Intel Xeon6 processors
- **REST API**: OpenAI-compatible completions endpoint
- **Autoscaling**: 1-3 pods based on request load

**Estimated time**: 10 minutes  
**Cost**: Minimal (uses existing CPU nodes)

## Prerequisites

Before starting, ensure you have:

### Required Tools

- **oc** - OpenShift CLI (version 4.12+)  
  Download: https://mirror.openshift.com/pub/openshift-v4/clients/oc/latest/
- **kubectl** - Kubernetes CLI (alternative to oc)  
  Download: https://kubernetes.io/docs/tasks/tools/
- **kustomize** - Kubernetes manifest customization tool  
  Download: https://kubectl.docs.kubernetes.io/installation/kustomize/

### Cluster Access

- OpenShift 4.12+ or Kubernetes 1.24+
- Cluster admin or sufficient permissions to create namespaces
- KServe 0.11+ installed (or OpenShift AI operator)
- Intel Xeon6 worker nodes (or any CPU nodes for testing)

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
   cd /path/to/project/deploy/cpu-inference
   ```

2. **Review configuration** (optional)

   The default configuration uses:
   - **Model**: TinyLlama/TinyLlama-1.1B-Chat-v1.0 (1.1B params)
   - **Resources**: 2-4 CPU cores, 4-8Gi memory
   - **Replicas**: 1-3 (autoscaling)

   To use a different model, edit `inference-service.yaml`:

   ```yaml
   env:
     - name: MODEL_NAME
       value: "TinyLlama/TinyLlama-1.1B-Chat-v1.0"  # Change this
   ```

   Approved models:
   - TinyLlama/TinyLlama-1.1B-Chat-v1.0 (1.1B)
   - microsoft/phi-2 (2.7B)
   - microsoft/Phi-3-mini-4k-instruct (3.8B)

3. **Deploy with Kustomize**

   ```bash
   # Preview what will be deployed
   kustomize build .

   # Deploy to cluster
   kustomize build . | oc apply -f -
   ```

   Expected output:
   ```
   namespace/intel-rh-cpu-inference created
   servingruntime.serving.kserve.io/vllm-cpu-runtime created
   inferenceservice.serving.kserve.io/cpu-inference-example created
   networkpolicy.networking.k8s.io/cpu-inference-netpol created
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
   oc get inferenceservice cpu-inference-example -n intel-rh-cpu-inference -w

   # Check pods
   oc get pods -n intel-rh-cpu-inference

   # View logs
   oc logs -n intel-rh-cpu-inference -l serving.kserve.io/inferenceservice=cpu-inference-example -f
   ```

   **Deployment is ready when**:
   ```
   NAME                     READY   URL
   cpu-inference-example    True    http://cpu-inference-example-intel-rh-cpu-inference.apps.cluster.com
   ```

   This may take 3-5 minutes while the model downloads (~2GB) and loads into memory.

## Test the Deployment

5. **Get the inference URL**

   ```bash
   # Retrieve the inference service URL
   ISVC_URL=$(oc get inferenceservice cpu-inference-example \
     -n intel-rh-cpu-inference \
     -o jsonpath='{.status.url}')

   echo "Inference URL: $ISVC_URL"
   ```

   Expected output:
   ```
   Inference URL: http://cpu-inference-example-intel-rh-cpu-inference.apps.your-cluster.com
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

7. **Test available models**

   ```bash
   # List available models
   curl $ISVC_URL/v1/models
   ```

   Expected output:
   ```json
   {
     "object": "list",
     "data": [
       {
         "id": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
         "object": "model",
         "created": 1234567890,
         "owned_by": "huggingface"
       }
     ]
   }
   ```

## Verify and Monitor

### Check Resource Usage

```bash
# View pod resource consumption
oc adm top pods -n intel-rh-cpu-inference

# Describe the inference service
oc describe inferenceservice cpu-inference-example -n intel-rh-cpu-inference
```

### View Metrics

```bash
# Get metrics endpoint
METRICS_URL=$(oc get route -n intel-rh-cpu-inference -o jsonpath='{.items[0].spec.host}')

# Fetch Prometheus metrics
curl http://$METRICS_URL:8080/metrics
```

Key metrics to watch:
- `inference_request_duration_seconds` - Request latency
- `inference_requests_total` - Total requests
- `inference_request_failure_total` - Failed requests

### Check Logs for Issues

```bash
# Follow logs in real-time
oc logs -n intel-rh-cpu-inference \
  -l serving.kserve.io/inferenceservice=cpu-inference-example \
  -f

# Get last 50 lines
oc logs -n intel-rh-cpu-inference \
  -l serving.kserve.io/inferenceservice=cpu-inference-example \
  --tail=50
```

## Troubleshooting

### Pods Not Starting

```bash
# Check events
oc get events -n intel-rh-cpu-inference --sort-by='.lastTimestamp'

# Describe pod for details
oc describe pod -n intel-rh-cpu-inference <pod-name>
```

**Common issues:**
- **ImagePullBackOff**: Image not accessible. Update `serving-runtime.yaml` with correct image reference.
- **Insufficient resources**: Node lacks CPU/memory. Reduce resource requests in `inference-service.yaml`.
- **Pending**: No available nodes. Check node selector matches cluster labels.

### Model Download Failing

If the model fails to download:

```bash
# Check network policy allows HTTPS egress
oc describe networkpolicy cpu-inference-netpol -n intel-rh-cpu-inference

# For private models, add HuggingFace token
oc create secret generic huggingface-secret \
  --from-literal=token=hf_your_token_here \
  -n intel-rh-cpu-inference

# Update inference-service.yaml to use secret
```

### Inference Returns Errors

Check logs for specific error messages:

```bash
oc logs -n intel-rh-cpu-inference \
  -l app.kubernetes.io/name=cpu-inference-example \
  --tail=100
```

**Common errors:**
- **Out of memory**: Increase memory limits or use smaller model
- **Model not found**: Verify MODEL_NAME matches HuggingFace model ID
- **Timeout**: Model loading takes time; increase readiness probe timeout

## Cleanup

### Remove the Deployment

```bash
# Delete all resources
kustomize build . | oc delete -f -

# Or delete the entire namespace
oc delete namespace intel-rh-cpu-inference
```

**Verify cleanup:**
```bash
oc get ns intel-rh-cpu-inference
# Should return: Error from server (NotFound)
```

## Next Steps

### Scale the Service

Edit `inference-service.yaml` to increase replicas:

```yaml
spec:
  predictor:
    minReplicas: 2  # Increased from 1
    maxReplicas: 10  # Increased from 3
```

Redeploy:
```bash
kustomize build . | oc apply -f -
```

### Deploy a Larger Model

Update `inference-service.yaml`:

```yaml
env:
  - name: MODEL_NAME
    value: "microsoft/phi-2"  # 2.7B parameters

resources:
  requests:
    cpu: "4"
    memory: "8Gi"
  limits:
    cpu: "8"
    memory: "16Gi"
```

### Try GPU Acceleration

For higher throughput, see the **Gaudi GPU quickstart** at:  
`docs/quickstarts/gaudi-hello-world/README.md`

### Integration with Applications

Use the OpenAI-compatible API from your application:

```python
import openai

client = openai.OpenAI(
    base_url="http://cpu-inference-example-intel-rh-cpu-inference.apps.cluster.com/v1",
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

All manifests are in `../../deploy/cpu-inference/`:

- `namespace.yaml` - Namespace definition
- `serving-runtime.yaml` - vLLM CPU runtime configuration
- `inference-service.yaml` - InferenceService example
- `network-policy.yaml` - Network isolation rules
- `kustomization.yaml` - Kustomize build configuration

## Support

- **Documentation**: See `deploy/cpu-inference/README.md` for detailed configuration
- **Issues**: Report bugs to your platform team
- **Model requests**: Submit approved model requests through official channels

---

**Platform**: Intel Xeon6 CPU Inference  
**Runtime**: vLLM CPU (transformers-based)  
**Orchestration**: KServe on OpenShift  
**Time to Deploy**: ~10 minutes
