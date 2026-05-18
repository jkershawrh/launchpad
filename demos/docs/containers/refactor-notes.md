# Refactor Notes - vLLM CPU Container

## Current Status: V1 - Simplified (transformers-only)

### Why Simplified Version?

Following TDD best practices: **RED → GREEN → REFACTOR**

vLLM has complex build dependencies that were blocking GREEN phase:
- PyTorch version conflicts
- Missing build-time attributes (`torch.version.xpu`)
- Long build times (10+ minutes)
- Multiple dependency iterations needed

**Decision**: Start with simpler implementation to:
1. ✅ Get tests GREEN quickly
2. ✅ Validate full TDD cycle works
3. ✅ Test OpenShift manifests
4. ✅ Create working quickstarts
5. 🔄 **Then** refactor to full vLLM

### V1 Implementation (Current)

**Stack**:
- PyTorch 2.3.1 (CPU-only)
- Transformers library
- Custom FastAPI server (`inference_server.py`)
- vLLM-compatible API endpoints

**Advantages**:
- ✅ Fast build (~3-5 min vs 10+ min)
- ✅ Simple dependencies
- ✅ Compatible API format
- ✅ Works on CPU
- ✅ Good for testing/validation

**Limitations**:
- ⚠️ Not optimized for high throughput
- ⚠️ No PagedAttention (vLLM's key feature)
- ⚠️ Lower tokens/sec than vLLM
- ⚠️ Higher memory usage per request

### V2 Plan (Future Refactor)

Once Stage 1 is GREEN and validated, refactor to one of:

**Option A: Pre-built vLLM wheels**
- Use official vLLM binary wheels
- Faster build, avoids source compilation
- Still get full vLLM features

**Option B: Multi-stage build**
- Build vLLM in builder stage
- Copy binaries to runtime stage
- Cleaner, smaller final image

**Option C: Official vLLM container**
- Use `vllm/vllm-openai:latest` as base
- Add our customizations
- Simplest approach

### Refactor Trigger

Refactor to full vLLM **after**:
- ✅ Stage 1 tests are GREEN (>= 90%)
- ✅ Manifests validated
- ✅ Quickstart tested
- ✅ Local inference working
- ✅ Stage gate passed

### API Compatibility

Current implementation matches vLLM OpenAI-compatible API:
- `POST /v1/completions` - Text completion
- `GET /v1/models` - List models
- `GET /health` - Health check

**Migration path**: When we refactor to full vLLM, API stays the same. Only internal implementation changes. No manifest/quickstart updates needed.

### Performance Expectations

**V1 (transformers)**:
- Small models (< 3B params): 5-15 tokens/sec
- Good for: demos, development, testing

**V2 (vLLM)**:
- Small models: 20-50 tokens/sec
- Good for: production, partners, benchmarks

### Testing Notes

All tests written for V1 will work with V2:
- Container build tests ✓
- Runtime tests ✓
- Security tests ✓
- API compatibility tests ✓

Only performance benchmarks may need threshold adjustments.

---

**TDD Adherence**: ✅ This refactor plan follows RED → GREEN → **REFACTOR** properly.
**Next Step**: Get V1 GREEN, pass stage gate, then refactor.
