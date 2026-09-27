# Multi-Agent Quickstart seat runtime

This chart adapts the immutable upstream Multi-Agent Quickstart source into a
Launchpad seat. It runs the orchestrator, three A2A agents, MCP server,
guardrails service, and participant UI in one pod while preserving a Service
for each protocol endpoint. Launchpad supplies model and service credentials
through a per-seat Secret and supplies ownership identity through Helm values.

The image repository and immutable digest are required at render time. The
chart never creates or serializes a Secret.

## Optional operations presentation

The 401 operations catalog item can enable `presentation.enabled` and supply a
second immutable image digest. That creates a separately owned Deployment,
Service, edge Route, and ingress policy. Its NGINX runtime proxies `/api` to the
seat-local orchestrator and injects the per-seat service token server-side, so
the browser never receives the token and the orchestrator does not need a
public Route for the presentation.

The presentation is disabled by default. Existing 301 seats render exactly the
same workload contract unless their catalog values explicitly enable it.
