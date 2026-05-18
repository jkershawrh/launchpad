# Intel-Red Hat AI Partner Demo

**Platform for Intel-Red Hat partner AI inference demos on OpenShift AI**

---

## Overview

The Intel-Red Hat AI Partner Demo provides **two optimized inference paths** for AI workloads on Red Hat OpenShift AI:

1. **CPU Path (Intel Xeon6)** - Cost-efficient inference for smaller models and latency-tolerant workloads
2. **Gaudi GPU Path (Intel Gaudi)** - High-performance inference for larger models and throughput-sensitive workloads

---

## Quick Start

### Prerequisites

- OpenShift cluster with OpenShift AI operator
- `oc` or `kubectl` CLI
- `kustomize`
- Python 3.9+ with `pytest`

### Deploy CPU Inference

```bash
cd red_hat_intel_partner_demo

# Deploy CPU path
oc apply -k deploy/cpu-inference

# Wait for ready
oc wait --for=condition=Ready inferenceservice/cpu-inference-example \
  -n intel-rh-cpu-inference --timeout=10m

# Test
cd docs/quickstarts/cpu-hello-world
./test.sh
```

### Deploy Gaudi Inference

```bash
# Verify Gaudi nodes
oc get nodes -o json | jq '.items[] | select(.status.allocatable["habana.ai/gaudi"] != null)'

# Deploy Gaudi path
oc apply -k deploy/gaudi-inference

# Wait for ready
oc wait --for=condition=Ready inferenceservice/gaudi-inference-example \
  -n intel-rh-gaudi-inference --timeout=15m
```

### Deploy with Ansible

```bash
cd ansible

# Discover cluster capabilities
ansible-playbook playbooks/discover-cluster.yaml

# Deploy CPU inference
ansible-playbook playbooks/deploy-cpu.yaml

# Deploy Gaudi inference
ansible-playbook playbooks/deploy-gaudi.yaml

# Health check
ansible-playbook playbooks/health-check.yaml
```

---

## Project Status

| Stage | Component | Status | Score |
|-------|-----------|--------|-------|
| 0 | Test Infrastructure | Complete | 100% |
| 1 | CPU Inference Path | Complete | 92.2% |
| 2 | Gaudi Inference Path | Complete | 100% |
| 3 | Demo Test Client | Complete | 100% |
| 4 | Cluster Discovery | Complete | 100% |
| 5 | Smoke Deploy | Blocked | - |
| 6 | Partner Pack | Pending | - |

**Overall**: 67% complete | **Blocker**: Awaiting Rackspace cluster access

---

## Performance Benchmarks

| Metric | CPU (Xeon6) | Gaudi GPU | Speedup |
|--------|-------------|-----------|---------|
| TTFT | 10-30s | < 2s | 5-15x |
| Throughput | 5-10 tok/s | 100+ tok/s | 10-20x |
| Concurrency | 3 requests | 5+ requests | Better |

---

## Repository Structure

```
red_hat_intel_partner_demo/
├── README.md
├── PROJECT_STATUS.md
├── Makefile
├── requirements.txt
│
├── containers/                      # Container images
│   ├── vllm-cpu/                    #   CPU inference (transformers-based)
│   └── vllm-gaudi/                  #   Gaudi inference (V1 mock + V2 production)
│
├── deploy/                          # OpenShift/Kubernetes manifests
│   ├── cpu-inference/               #   CPU path (kustomize)
│   └── gaudi-inference/             #   Gaudi path (kustomize)
│
├── ansible/                         # Ansible automation
│   ├── playbooks/                   #   Deploy, discover, teardown, health-check
│   ├── roles/                       #   Reusable roles per function
│   └── inventory/                   #   Cluster connection info
│
├── scripts/                         # Utility scripts
│   ├── build-images.sh              #   Container build/push automation
│   └── discover-cluster.sh          #   Cluster discovery
│
├── tools/                           # Developer/demo tools
│   └── inference-test-client/       #   Benchmark client with TTFT/throughput
│
├── docs/                            # Documentation
│   ├── quickstarts/                 #   Step-by-step deployment guides
│   ├── architecture/                #   Golden paths, stakeholder map
│   ├── validation-reports/          #   TDD stage validation reports
│   └── containers/                  #   Container build docs
│
└── tests/                           # Test suites (248 tests)
    ├── test_*.py                    #   Pytest test files
    ├── rubrics/                     #   Quality scoring
    ├── fixtures/                    #   Test data
    └── validation_matrix.yaml       #   Stage gate criteria
```

---

## Running Tests

```bash
# Install dependencies
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run all local tests
pytest tests/ -v

# Run specific stages
pytest tests/test_cpu_manifests.py -v      # CPU manifests
pytest tests/test_gaudi_manifests.py -v    # Gaudi manifests
pytest tests/test_inference_client.py -v   # Demo client
pytest tests/test_discovery.py -v          # Discovery
pytest tests/test_build_script.py -v       # Build script
```

---

## Documentation

- [CPU Quickstart](docs/quickstarts/cpu-hello-world/README.md)
- [Gaudi Quickstart](docs/quickstarts/gaudi-hello-world/README.md)
- [Golden Paths](docs/architecture/golden-paths.md)
- [Stakeholder Map](docs/architecture/stakeholder-map.md)
- [TDD Iterations](docs/tdd-iterations.md)
- [CPU Manifest Details](deploy/cpu-inference/README.md)
- [Gaudi Manifest Details](deploy/gaudi-inference/README.md)

---

**Status**: Awaiting Rackspace cluster access for Stage 5 smoke deployment  
**Team**: Red Hat AI Infrastructure  
**License**: Red Hat Internal
