# Participant access availability contract

This local-only staging slice separates a denied claim from an unavailable
access broker. It does not change the claim, seat, or entitlement protocol.

| Case | Participant gateway result |
| --- | --- |
| No entitlement for an otherwise reachable order (`403`) | Show the join/add-code form. |
| Access broker connection or timeout failure | Return `503`; do not imply the code is invalid. |
| Access broker returns an error during My Lab Access lookup | Return `503`; do not claim that the identity has zero active labs. |

The RED run of `test_public_gateway_availability_contract.py` produced two
expected failures: the order home returned `200`/join form on broker `503`,
and an unhandled broker connection failure escaped the request. The GREEN
run passed all 43 tests across the new contract, existing public gateway,
and 1/5/25/30-seat participant journey suites. No cluster was contacted.

This is **GREEN-local**, not live certification. A staging browser run still
needs to prove that an actual broker outage surfaces a retryable error and
that normal join, resume, and code-denial journeys remain intact. The live
pilot workshops must not be used for that fault injection.
