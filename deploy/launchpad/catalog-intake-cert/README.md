# Catalog intake certification boundary

This package is an isolated, non-production proof environment for Quickstart
repository discovery. It cannot publish a catalog item or provision a lab.
Runtime pods have no service-account token, Secret mount, database access,
registry-publisher access, or workshop access.

The worker image is built from binary source, scanned, and referenced by its
immutable registry digest. Replace `CATALOG_INTAKE_WORKER_IMAGE` in the rendered
manifest with that digest before applying the proxy Deployment. Never deploy a
mutable tag into the runtime objects.

The default-deny selector intentionally covers only the discovery worker and
its allowlisting proxy. OpenShift's temporary build pod is a separate supply
path and requires API access to receive binary input and publish the resulting
image. The per-attempt worker NetworkPolicy still permits only OpenShift DNS
and the proxy. The proxy rejects all methods except HTTPS `CONNECT`, permits
only `github.com` and `api.github.com`, rejects non-global resolved addresses,
and cannot reach private cluster ranges.

The trusted dispatcher and receipt collector remain disabled. Until their
fault and cleanup tests are green, operators may run only manual,
analysis-only certification attempts in this namespace.
