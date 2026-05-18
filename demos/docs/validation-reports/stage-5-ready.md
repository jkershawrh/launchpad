# Stage 5: Smoke Deploy - READY (Blocked on Cluster Access)

## Status

**Stage 5 Status**: ⏳ **READY TO EXECUTE - BLOCKED ON CLUSTER ACCESS**  
**Test Files Created**: ✅ **RED PHASE COMPLETE**  
**Blocker**: ❌ **No access to Rackspace OpenShift AI cluster**  
**Date Prepared**: 2026-05-04

---

## Executive Summary

Stage 5 test files have been written following TDD methodology (RED phase complete). Tests are ready to run once cluster access is obtained. This stage validates both CPU and Gaudi inference paths on the real Rackspace OpenShift AI cluster.

**Test Files Ready**:
- ✅ `tests/test_cpu_deploy_cluster.py` (29 tests) - CPU path deployment validation
- ✅ `tests/test_gaudi_deploy_cluster.py` (30 tests) - Gaudi path deployment validation

**Total Stage 5 Tests**: 59 tests (RED phase, will fail until deployed)

---

## Prerequisites

### Required Access

1. **Rackspace OpenShift AI Cluster**
   - Cluster URL and credentials
   - `oc` CLI logged in to cluster
   - Sufficient permissions to create namespaces and deploy resources

2. **Cluster Requirements** (will be verified by tests):
   - OpenShift AI operator installed
   - KServe available
   - CPU worker nodes (Xeon6)
   - Gaudi GPU worker nodes
   - Habana device plugin installed

3. **Local Tools**:
   - `oc` or `kubectl` CLI
   - `kustomize` CLI
   - Python 3.9+ with pytest
   - `requests` library

---

## Stage 5 Workflow

### Step 1: Obtain Cluster Access

**Action**: Login to Rackspace OpenShift AI cluster
```bash
oc login https://api.<cluster-url>:6443 --username=<user> --password=<pass>
```

**Verification**:
```bash
oc cluster-info
oc get nodes
```

---

### Step 2: Run Discovery Script

**Action**: Discover cluster configuration
```bash
./scripts/discover-cluster.sh --output cluster-info.yaml --verbose
```

**Output**: `cluster-info.yaml` with:
- Cluster version and API URL
- Node counts (CPU and Gaudi)
- Node labels for scheduling
- Operator installation status
- Image registry information

**Review**:
```bash
cat cluster-info.yaml
```

**Check for**:
- `gaudi_count > 0` (Gaudi nodes available)
- `habana_device_plugin.installed: true` (device plugin running)
- `openshift_ai.installed: true` (OpenShift AI ready)

---

### Step 3: Update Manifests (Fill [TBD] Placeholders)

**Review cluster-info.yaml findings**:
```bash
# Check Gaudi node labels
grep -A 10 "gaudi_nodes:" cluster-info.yaml
```

**Update manifests if needed**:
- `deploy/cpu-inference/*.yaml` - Update node selectors if needed
- `deploy/gaudi-inference/*.yaml` - Update Gaudi node labels
- Update image references if using internal registry

**Example**: If Gaudi nodes have label `intel.feature.node.kubernetes.io/gaudi: "true"`, update `gaudi-inference/serving-runtime.yaml`:
```yaml
nodeSelector:
  node-role.kubernetes.io/worker: ""
  intel.feature.node.kubernetes.io/gaudi: "true"  # ADD THIS LINE
```

---

### Step 4: Deploy CPU Inference Path (Stage 5.1)

**Action**: Deploy CPU path using quickstart
```bash
cd quickstarts/cpu-hello-world
./deploy.sh
```

**Or manually**:
```bash
oc apply -k deploy/cpu-inference
```

**Verify deployment**:
```bash
oc get namespace intel-rh-cpu-inference
oc get inferenceservice -n intel-rh-cpu-inference
oc get pods -n intel-rh-cpu-inference
```

**Wait for ready**:
```bash
oc wait --for=condition=Ready inferenceservice/cpu-inference-example \
  -n intel-rh-cpu-inference --timeout=10m
```

---

### Step 5: Test CPU Path

**Run test suite**:
```bash
pytest tests/test_cpu_deploy_cluster.py -v
```

**Expected results**:
- All 29 tests should pass
- Pod running on CPU node (NOT Gaudi)
- InferenceService ready with URL
- Health, models, completions endpoints working
- TTFT < 30s for TinyLlama
- Throughput >= 5 tokens/sec
- Pod stays running for 5 minutes

**Manual test** (alternative):
```bash
cd quickstarts/cpu-hello-world
./test.sh
```

**Or use test client**:
```bash
# Get InferenceService URL
CPU_URL=$(oc get inferenceservice cpu-inference-example \
  -n intel-rh-cpu-inference -o jsonpath='{.status.url}')

# Run benchmark
python3 tools/inference-test-client/client.py \
  --url $CPU_URL \
  --benchmark \
  --num-requests 20 \
  --json > cpu-benchmark-results.json
```

---

### Step 6: Deploy Gaudi Inference Path (Stage 5.2)

**Prerequisite check**:
```bash
# Verify Gaudi nodes available
oc get nodes -o json | jq '.items[] | select(.status.allocatable["habana.ai/gaudi"] != null) | .metadata.name'

# Verify Habana device plugin running
oc get ds -A | grep habana
```

**Action**: Deploy Gaudi path using quickstart
```bash
cd quickstarts/gaudi-hello-world
./deploy.sh
```

**Or manually**:
```bash
oc apply -k deploy/gaudi-inference
```

**Verify deployment**:
```bash
oc get namespace intel-rh-gaudi-inference
oc get inferenceservice -n intel-rh-gaudi-inference
oc get pods -n intel-rh-gaudi-inference
```

**Wait for ready** (may take longer than CPU):
```bash
oc wait --for=condition=Ready inferenceservice/gaudi-inference-example \
  -n intel-rh-gaudi-inference --timeout=15m
```

---

### Step 7: Test Gaudi Path

**Run test suite**:
```bash
pytest tests/test_gaudi_deploy_cluster.py -v
```

**Expected results**:
- All 30 tests should pass
- Pod running on Gaudi GPU node
- Pod has `habana.ai/gaudi: "1"` resource assigned
- InferenceService ready with URL
- Health, models, completions endpoints working
- **TTFT < 5s** for TinyLlama (much faster than CPU)
- **Throughput >= 50 tokens/sec** (10x faster than CPU)
- Pod stays running for 5 minutes
- Higher concurrency (5 concurrent requests vs 3 for CPU)

**Manual test** (alternative):
```bash
cd quickstarts/gaudi-hello-world
./test.sh
```

**Or use test client**:
```bash
# Get InferenceService URL
GAUDI_URL=$(oc get inferenceservice gaudi-inference-example \
  -n intel-rh-gaudi-inference -o jsonpath='{.status.url}')

# Run benchmark
python3 tools/inference-test-client/client.py \
  --url $GAUDI_URL \
  --benchmark \
  --num-requests 20 \
  --json > gaudi-benchmark-results.json
```

---

### Step 8: Compare CPU vs Gaudi Performance

**Run comparison**:
```bash
# Compare benchmark results
echo "=== CPU Results ==="
cat cpu-benchmark-results.json | jq '.benchmark | {ttft_mean_ms: .ttft.mean_ms, throughput: .throughput.mean_tokens_per_second}'

echo "=== Gaudi Results ==="
cat gaudi-benchmark-results.json | jq '.benchmark | {ttft_mean_ms: .ttft.mean_ms, throughput: .throughput.mean_tokens_per_second}'
```

**Expected comparison** (approximate):
| Metric | CPU | Gaudi | Speedup |
|--------|-----|-------|---------|
| TTFT (ms) | 10,000-30,000 | < 2,000 | 5-15x |
| Throughput (tok/s) | 5-10 | 50-100+ | 10-20x |
| Concurrency | 3 | 5+ | Better |

---

### Step 9: Capture Deployment Details

**Document findings**:

1. **Cluster Information**:
   ```bash
   oc version
   oc get nodes -o wide
   ```

2. **Container Images** (get actual digests):
   ```bash
   # CPU container
   oc get pod -n intel-rh-cpu-inference -o jsonpath='{.items[0].spec.containers[0].image}'
   
   # Gaudi container
   oc get pod -n intel-rh-gaudi-inference -o jsonpath='{.items[0].spec.containers[0].image}'
   ```

3. **Node Labels** (actual labels discovered):
   ```bash
   # Gaudi node labels
   oc get nodes -o json | jq '.items[] | select(.status.allocatable["habana.ai/gaudi"] != null) | {name: .metadata.name, labels: .metadata.labels}'
   ```

4. **Performance Benchmarks**:
   - Save `cpu-benchmark-results.json`
   - Save `gaudi-benchmark-results.json`
   - Document TTFT and throughput for both paths

5. **Screenshots/Logs**:
   - OpenShift AI dashboard showing deployments
   - InferenceService status
   - Pod logs showing successful inference

---

### Step 10: Create Validation Report

**Create**: `STAGE_5_VALIDATION.md`

**Contents**:
- Test results (59/59 passing expected)
- Actual vs expected performance metrics
- Cluster configuration discovered
- Container image digests
- Node labels used
- Any issues encountered and resolved
- Screenshots and evidence

**Calculate validation score**:
- Prerequisites: 4-5 tests
- Deployment: 5-6 tests per path
- Pod status: 4-5 tests per path
- InferenceService status: 2 tests per path
- Endpoints: 3 tests per path
- Performance: 4 tests per path
- Observability: 2 tests per path

**Expected score**: 95-100% (59/59 or 57/59 tests passing)

**Threshold**: 90%

---

## Test File Details

### test_cpu_deploy_cluster.py (29 tests)

**Test Classes**:
1. `TestPrerequisites` (4 tests)
   - Cluster access
   - Cluster info exists
   - CPU nodes available
   - OpenShift AI installed

2. `TestDeployment` (5 tests)
   - Manifests exist
   - Kustomize builds
   - Namespace created
   - ServingRuntime created
   - InferenceService created

3. `TestPodStatus` (4 tests)
   - Pods exist
   - Pods running
   - Pod on CPU node (NOT Gaudi)
   - Pod stays running 5 minutes

4. `TestInferenceServiceStatus` (2 tests)
   - InferenceService ready
   - InferenceService has URL

5. `TestInferenceEndpoints` (3 tests)
   - Health endpoint responds
   - Models endpoint responds
   - Completions endpoint generates text

6. `TestPerformanceMetrics` (4 tests)
   - TTFT < 30s
   - Throughput measured
   - Concurrent requests (3 simultaneous)

7. `TestObservability` (2 tests)
   - Pod logs available
   - Metrics endpoint exists (optional)

8. Validation matrix tracker (1 test)

---

### test_gaudi_deploy_cluster.py (30 tests)

**Test Classes** (similar to CPU but with Gaudi-specific checks):
1. `TestPrerequisites` (5 tests)
   - Cluster access
   - Cluster info exists
   - **Gaudi nodes available** ⚡
   - OpenShift AI installed
   - **Habana device plugin installed** ⚡

2. `TestDeployment` (5 tests)
   - Same as CPU

3. `TestPodStatus` (5 tests)
   - Pods exist
   - Pods running (10 min timeout)
   - **Pod on Gaudi GPU node** ⚡
   - **Pod has habana.ai/gaudi resource** ⚡
   - Pod stays running 5 minutes

4. `TestInferenceServiceStatus` (2 tests)
   - InferenceService ready (15 min timeout)
   - InferenceService has URL

5. `TestInferenceEndpoints` (3 tests)
   - Health endpoint responds
   - Models endpoint responds
   - Completions endpoint generates text

6. `TestPerformanceMetrics` (5 tests)
   - **TTFT < 5s** (vs < 30s for CPU) ⚡
   - **Throughput >= 50 tok/s** (vs >= 5 for CPU) ⚡
   - Concurrent requests (5 vs 3 for CPU) ⚡
   - **Gaudi faster than CPU baseline** ⚡

7. `TestGaudiSpecificFeatures` (2 tests)
   - Habana device visible in pod
   - Gaudi GPU utilization

8. `TestObservability` (2 tests)
   - Pod logs available
   - Metrics endpoint exists (optional)

9. Validation matrix tracker (1 test)

**⚡ = Gaudi-specific test**

---

## Expected Issues and Solutions

### Issue: No Gaudi Nodes Available

**Symptom**: `test_cluster_has_gaudi_nodes` fails

**Solution**:
- Verify cluster has Gaudi hardware
- Check node labels: `oc get nodes -L habana.ai/gaudi`
- May need to request Gaudi nodes from cluster admin
- Can proceed with CPU-only deployment if no Gaudi available

---

### Issue: Habana Device Plugin Not Running

**Symptom**: `test_habana_device_plugin_installed` fails

**Solution**:
- Check DaemonSet: `oc get ds -A | grep habana`
- May need to install Habana device plugin
- Refer to Habana documentation for installation
- Cannot proceed with Gaudi deployment without device plugin

---

### Issue: InferenceService Not Ready

**Symptom**: `test_inference_service_ready` fails after timeout

**Solution**:
- Check pod status: `oc get pods -n <namespace>`
- Check pod logs: `oc logs <pod-name> -n <namespace>`
- Common issues:
  - Image pull errors (check image registry)
  - Model download timeout (HuggingFace connectivity)
  - Insufficient resources (check node capacity)
- Increase timeout if model is large

---

### Issue: Performance Not Meeting Targets

**Symptom**: TTFT or throughput tests fail

**Solution**:
- **CPU too slow**: May be expected for larger models, adjust thresholds
- **Gaudi too slow**: Check GPU assignment, verify not running in mock mode
- Check pod resource limits
- Verify no resource contention on nodes
- May need to tune model or inference parameters

---

### Issue: Image Pull Errors

**Symptom**: Pods stuck in `ImagePullBackOff`

**Solution**:
- Check image exists: `podman images | grep vllm`
- Push to cluster registry or external registry (quay.io)
- Update manifest with correct image URL
- Verify image pull secrets if using private registry

---

## Success Criteria

### Minimum (90% threshold)

- ✅ Both deployments created (CPU and Gaudi)
- ✅ Both InferenceServices ready
- ✅ Both endpoints responding (health, models, completions)
- ✅ CPU path functional with reasonable performance
- ✅ Gaudi path functional (if Gaudi available)
- ✅ 53/59 tests passing (90%)

### Target (100%)

- ✅ All 59 tests passing
- ✅ CPU TTFT < 30s
- ✅ Gaudi TTFT < 5s
- ✅ Gaudi 5-10x faster than CPU
- ✅ Both paths stable for 5+ minutes
- ✅ Concurrency tests pass
- ✅ Performance benchmarks captured

---

## Post-Stage 5 Deliverables

Once Stage 5 completes successfully:

1. **STAGE_5_VALIDATION.md** - Validation report with actual results
2. **cluster-info.yaml** - Actual cluster configuration
3. **cpu-benchmark-results.json** - CPU performance metrics
4. **gaudi-benchmark-results.json** - Gaudi performance metrics
5. **Updated manifests** - No [TBD] placeholders, actual values
6. **Container image digests** - Actual deployed images
7. **Screenshots** - Evidence of successful deployment
8. **Lessons learned** - Any issues and resolutions

---

## Next Stage

**Stage 6: Partner Welcome Pack**
- Final documentation bundle
- Deployment guides with real values
- Performance benchmarks
- Partner onboarding instructions
- Support information

---

## Summary

**Status**: ⏳ **RED PHASE COMPLETE - AWAITING CLUSTER ACCESS**

**Ready to Execute**:
- ✅ 59 tests written
- ✅ Discovery script ready
- ✅ All manifests prepared
- ✅ Quickstarts documented
- ✅ Test client ready

**Blockers**:
- ❌ No cluster access at Rackspace
- ⏳ Waiting for credentials and URL

**Time Estimate**: 1-2 days once cluster access obtained

**Confidence**: **VERY HIGH** - All preparation complete, clear workflow documented

---

**Next Action**: **OBTAIN RACKSPACE OPENSHIFT AI CLUSTER ACCESS**

Once access obtained, follow this document step-by-step to complete Stage 5 validation.
