# Launchpad security threat model

The authoritative, versioned threat model is
[`contracts/security-threat-model-v1.yaml`](../contracts/security-threat-model-v1.yaml).
It covers public participant access, the control plane, the execution fleet,
the model plane, artifact supply, governed data flows, and support access.

The contract is deliberately fail-closed. Every surface must name its owner,
trust boundaries, protected assets, threats, mitigations, verification cases,
and unresolved risks. Referenced controls and verification cases must resolve,
and every evidence path must exist in the repository. Structural validity is
only `GREEN-local`; it does not certify a live environment or make the release
production-eligible.

Run the local check with:

```console
python3 scripts/validate_security_threat_model.py
```

The report remains release-blocking while any critical or high risk is open,
any verification is only planned, or independent security review is absent.
The current open boundaries include the dedicated public staging-tunnel run,
fleet credential rotation, signed/SBOM-backed artifacts and cold pulls,
model/tool abuse testing, durable audit retention, and time-bounded support
access. Those are documented risks, not implied certifications.

The current pilot path for investigating failures without restoring raw
browser log access is defined in
[`operator-log-access.md`](operator-log-access.md). Its future support UI is a
separate security gate, not an implemented capability.

## Change control

Review and version the contract whenever an identity flow, network boundary,
data classification, model/tool integration, registry authority, support path,
or release stage changes. New threats must first receive a failing validation
or abuse test. Closing a risk requires immutable evidence from its stated
decision gate; deleting the risk is not evidence.
