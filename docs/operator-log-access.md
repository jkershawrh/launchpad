# Operator log access boundary

Launchpad does not expose raw container logs through its requester, participant,
or admin browser APIs. The former admin container-log endpoint is denied; a
generic capacity or cluster-inspection error in the UI is not a reason to
restore raw log streaming to the browser.

For pilot troubleshooting, an authorized cluster operator should use the
organization-approved OpenShift logging or cluster-audit interface directly,
within their existing cluster permissions. Limit the lookup to the affected
cluster, namespace, workload, and incident time window. Record the support
ticket, operator identity, access time, target, and outcome in the incident
record. Do not paste raw logs, credentials, participant email, codes, model
prompts, or tokens into a Launchpad issue or evidence manifest. Redact any
excerpt before attaching it to a support case.

A future Launchpad support UI is a separate gated change. Before enabling it,
prove all of the following in local, integration, and live security tests:

- Dedicated support role and just-in-time, time-bounded authorization; no
  requester, instructor, or participant access.
- Server-side cluster/namespace allow-listing and bounded time/size queries;
  no arbitrary pod, namespace, or cluster selection.
- Structured redaction before data leaves the logging boundary, with abuse
  tests for credentials, public codes, emails, model prompts, and tool output.
- Audit of every query and export, retention limits, and incident correlation.
- Cross-tenant denial, expired-access denial, and independent security review.

This document defines the intended access path and release gate. It does not
assert that a central logging stack, just-in-time role, or Launchpad support
UI is deployed or certified today.
