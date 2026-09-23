# Network Operations Agent: Flightpath one-seat certification

Certification date: 2026-09-23  
Maximum certified seats: 1  
Execution cluster: Flightpath  
Inference path: Flightpath LiteLLM gateway to Flightpath CPU vLLM  
Model: `granite-3.2-8b-tools`

## Immutable release

- Source revision: `1f24514abf5ba49955f22c3e5034bdb425725a71`
- Tested application code revision: `4ae303791d2b0060d0a198852f16dc6ef4ffefa4`
- Image digest: `sha256:8595d9a490b6d300ca9d821249e97b5d5634239012c91decede7995f60228bbb`
- Launchpad request: `aa758d2c-b197-492c-9866-0371b086d1d6`
- Launchpad session: `34270633-314d-4e29-9ebc-c3b0843ee4c5`

The source revision differs from the tested application code revision only by
this certification documentation and status update. The deployed application
code and immutable image are unchanged.

## Evidence

- Remote source validation, workload discovery, catalog drift, Showroom
  structure, and the complete Antora build passed.
- All 52 source-owned unit, contract, MCP, HTTP, publication, and chart tests
  passed.
- The application and diagnostics pods were `1/1 Running`; Showroom was `4/4
  Running`; both participant Routes were admitted.
- The runtime Secret selected
  `launchpad-candidate-maas.launchpad-flightpath-candidate.svc` and did not use
  RACMaaS or the Arena direct-model endpoint.
- Missing and invalid gateway keys returned HTTP 401. The issued per-seat
  virtual key returned HTTP 200.
- Both synthetic scenarios returned the correct distinct hypothesis, cited
  current tool observations and revisioned historical evidence, required human
  review, and executed no action. Each scored 8/8 under the repository rubric.
- Unapproved live-input mode returned HTTP 400.
- The diagnostics MCP Service had no Route and was protected by NetworkPolicy.
- Reclaim completed, the LiteLLM virtual key received a confirmed revocation,
  no key remained in the session, the tenant namespace was deleted, and no
  Argo CD application remained.

## Boundary

This receipt certifies one Flightpath seat only. It does not certify five or
25 seats, concurrent provisioning, performance, latency, MTTR, hardware
acceleration, or real-network remediation. RACMaaS is outside this delivery
path.
