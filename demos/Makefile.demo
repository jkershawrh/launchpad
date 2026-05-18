# Makefile for Intel-Red Hat Partner AI Demo Platform
# Provides automated testing and validation for stage gates

.PHONY: help test-all test-stage-0 test-stage-1 test-stage-2 test-stage-3 \
        test-overdrive clean install lint format security-scan

# Default target
help:
	@echo "Intel-Red Hat Partner AI Demo Platform - Make Targets"
	@echo ""
	@echo "Testing:"
	@echo "  make test-all          - Run all tests (regression suite)"
	@echo "  make test-stage-0      - Test Stage 0: Test Infrastructure"
	@echo "  make test-stage-1      - Test Stage 1: CPU Inference Path"
	@echo "  make test-stage-2      - Test Stage 2: Gaudi Inference Path"
	@echo "  make test-stage-3      - Test Stage 3: Demo Client"
	@echo "  make test-stage-4      - Test Stage 4: Discovery Tooling"
	@echo ""
	@echo "Development:"
	@echo "  make install           - Install Python dependencies"
	@echo "  make lint              - Run linters (flake8, pylint)"
	@echo "  make format            - Format code (black, isort)"
	@echo "  make security-scan     - Run security scans on containers"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean             - Remove generated files and caches"

# Python virtual environment
VENV := venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest

# Test configuration
PYTEST_ARGS := -v --tb=short
PYTEST_COV_ARGS := --cov=. --cov-report=term-missing --cov-report=html

# Create virtual environment
$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

# Install dependencies
install: $(VENV)/bin/activate
	$(PIP) install pytest pytest-cov pyyaml requests
	$(PIP) install flake8 pylint black isort
	@echo "Dependencies installed in $(VENV)"

# Stage 0: Test Infrastructure
test-stage-0: install
	@echo "========================================="
	@echo "Testing Stage 0: Test Infrastructure"
	@echo "========================================="
	$(PYTEST) $(PYTEST_ARGS) tests/test_framework.py
	@echo ""
	@echo "Stage 0 tests complete. Check validation matrix for pass/fail."

# Stage 1: CPU Inference Path
test-stage-1: install
	@echo "========================================="
	@echo "Testing Stage 1: CPU Inference Path"
	@echo "========================================="
	@echo "Running container tests..."
	$(PYTEST) $(PYTEST_ARGS) tests/test_vllm_cpu_container.py
	@echo ""
	@echo "Running local inference tests..."
	$(PYTEST) $(PYTEST_ARGS) tests/test_cpu_inference_local.py
	@echo ""
	@echo "Running manifest tests..."
	$(PYTEST) $(PYTEST_ARGS) tests/test_cpu_manifests.py
	@echo ""
	@echo "Running quickstart tests..."
	$(PYTEST) $(PYTEST_ARGS) tests/test_cpu_quickstart.py
	@echo ""
	@echo "Stage 1 tests complete. Check validation matrix for pass/fail."

# Stage 2: Gaudi Inference Path
test-stage-2: install
	@echo "========================================="
	@echo "Testing Stage 2: Gaudi Inference Path"
	@echo "========================================="
	@echo "Running container tests..."
	$(PYTEST) $(PYTEST_ARGS) tests/test_vllm_gaudi_container.py
	@echo ""
	@echo "Running local inference tests..."
	$(PYTEST) $(PYTEST_ARGS) tests/test_gaudi_inference_local.py
	@echo ""
	@echo "Running manifest tests..."
	$(PYTEST) $(PYTEST_ARGS) tests/test_gaudi_manifests.py
	@echo ""
	@echo "Running quickstart tests..."
	$(PYTEST) $(PYTEST_ARGS) tests/test_gaudi_quickstart.py
	@echo ""
	@echo "Stage 2 tests complete. Check validation matrix for pass/fail."

# Stage 3: Demo Client
test-stage-3: install
	@echo "========================================="
	@echo "Testing Stage 3: Demo Client"
	@echo "========================================="
	$(PYTEST) $(PYTEST_ARGS) tests/test_inference_client.py
	@echo ""
	@echo "Stage 3 tests complete. Check validation matrix for pass/fail."

# Stage 4: Discovery Tooling
test-stage-4: install
	@echo "========================================="
	@echo "Testing Stage 4: Discovery Tooling"
	@echo "========================================="
	$(PYTEST) $(PYTEST_ARGS) tests/test_discovery.py
	@echo ""
	@echo "Stage 4 tests complete. Check validation matrix for pass/fail."

# Run all tests (regression suite)
test-all: install
	@echo "========================================="
	@echo "Running Full Regression Test Suite"
	@echo "========================================="
	$(PYTEST) $(PYTEST_ARGS) $(PYTEST_COV_ARGS) tests/
	@echo ""
	@echo "All tests complete. See coverage report in htmlcov/index.html"

# Linting
lint: install
	@echo "Running flake8..."
	-$(VENV)/bin/flake8 tests/ tools/ containers/ --max-line-length=100 --exclude=venv
	@echo "Running pylint..."
	-$(VENV)/bin/pylint tests/ --disable=C0111

# Code formatting
format: install
	@echo "Formatting with black..."
	$(VENV)/bin/black tests/ tools/ --line-length=100
	@echo "Sorting imports with isort..."
	$(VENV)/bin/isort tests/ tools/

# Security scanning
security-scan:
	@echo "Running security scans on containers..."
	@echo "Checking if trivy is installed..."
	@which trivy || (echo "ERROR: trivy not installed. Install with: brew install trivy"; exit 1)
	@echo ""
	@echo "Scanning vLLM CPU container (if built)..."
	-trivy image localhost/vllm-cpu:latest --severity CRITICAL,HIGH
	@echo ""
	@echo "Scanning vLLM Gaudi container (if built)..."
	-trivy image localhost/vllm-gaudi:latest --severity CRITICAL,HIGH

# Clean generated files
clean:
	@echo "Cleaning generated files..."
	rm -rf $(VENV)
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "Clean complete."

# StarGate Overdrive Lite
test-overdrive: install
	@echo "===================================================================="
	@echo "  StarGate Overdrive Lite — Lane Evaluation Tests"
	@echo "===================================================================="
	$(PYTEST) $(PYTEST_ARGS) tests/test_overdrive_models.py
	$(PYTEST) $(PYTEST_ARGS) tests/test_overdrive_matrix.py
	$(PYTEST) $(PYTEST_ARGS) tests/test_overdrive_rubric.py
	$(PYTEST) $(PYTEST_ARGS) tests/test_overdrive_engine.py
	$(PYTEST) $(PYTEST_ARGS) tests/test_overdrive_evidence.py
	$(PYTEST) $(PYTEST_ARGS) tests/test_overdrive_report.py
	$(PYTEST) $(PYTEST_ARGS) tests/test_overdrive_regression.py
	@echo "Overdrive Lite tests complete."

test-overdrive-full: test-overdrive
	$(PYTEST) $(PYTEST_ARGS) tests/test_overdrive_api.py
	$(PYTEST) $(PYTEST_ARGS) tests/test_overdrive_frontend.py
	$(PYTEST) $(PYTEST_ARGS) tests/test_postprocessors.py
	$(PYTEST) $(PYTEST_ARGS) tests/test_tekton_pipeline.py
	$(PYTEST) $(PYTEST_ARGS) tests/test_cluster_deployment.py
	@echo "Overdrive full test suite complete."

check-overdrive:
	@echo "Validating Overdrive Lite..."
	@$(PYTHON) -m gateway.overdrive validate-rubrics
	@$(PYTHON) -m gateway.overdrive run-e2e-fixture tests/fixtures/e2e/mixed_routing.yaml
	@echo "✓ Overdrive Lite PASSED"

# Check stage gate status
check-stage-0:
	@echo "Checking Stage 0 gate status..."
	@$(PYTEST) tests/test_framework.py -v && echo "✓ Stage 0 PASSED" || echo "✗ Stage 0 FAILED"

# Cluster deployment (OpenShift)
deploy-pipeline:
	@echo "Applying Tekton pipeline..."
	oc apply -f deploy/pipelines/pipeline.yaml -n intel-rh-demo
	@echo "Pipeline applied. Run 'make deploy-run' to trigger a build."

deploy-run:
	@echo "Triggering pipeline run..."
	oc create -f deploy/pipelines/pipelinerun.yaml -n intel-rh-demo
	@echo "Pipeline run created. Watch with: tkn pipelinerun logs -f -n intel-rh-demo"

deploy-manifests:
	@echo "Applying cluster manifests via Kustomize..."
	oc apply -k deploy/cluster/ --dry-run=client
	@echo "Dry run passed. Run 'oc apply -k deploy/cluster/' to apply."

deploy-monitoring:
	oc apply -f deploy/observability/servicemonitor.yaml -n intel-rh-demo
	@echo "ServiceMonitor applied."

check-stage-1:
	@echo "Checking Stage 1 gate status..."
	@$(PYTEST) tests/test_vllm_cpu_container.py tests/test_cpu_inference_local.py \
	           tests/test_cpu_manifests.py tests/test_cpu_quickstart.py -v \
	           && echo "✓ Stage 1 PASSED" || echo "✗ Stage 1 FAILED"
