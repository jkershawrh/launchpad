# Arena MaaS bootstrap gate

Status: **shared prerequisites ready; candidate model path GREEN; release not certified** (2026-09-22). This is a shared infrastructure work item plus a candidate-scoped MaaS proof, not certification of the Hybrid Fraud catalog item. No live model, workshop, or Launchpad inference route was redirected during bootstrap or candidate validation.

## Applied outcome

- Red Hat Connectivity Link 1.4.3, Authorino 1.4.3, DNS Operator 1.4.2, and Limitador 1.4.2 installed successfully. The former community Authorino 0.16.0 had no `Authorino` or `AuthConfig` instances and was replaced by the supported Red Hat subscription.
- `Kuadrant/kuadrant` and TLS-enabled `Authorino/authorino` are Ready in `kuadrant-system`.
- The existing on-prem MaaS Gateway was converted from a permanently pending LoadBalancer Service to the documented ClusterIP + re-encrypt OpenShift Route pattern. `https://maas.apps.arena.fm2aihpcsed.com` reaches the gateway; its MaaS API route is attached through an explicit namespace selector. Missing and invalid credentials both return HTTP 401.
- Dedicated `PostgresCluster/launchpad-maas-db` runs two PostgreSQL 15 instances with separate data volumes, a pgBackRest repository, weekly full backups, daily incremental backups, and a completed initial backup. It does not reuse Launchpad or `sas-ram-db`. The repository is still on Arena NFS and is not off-cluster DR.
- OpenShift AI's current field `spec.components.aigateway.modelsAsAService.managementState` is `Managed`. `AITenant/models-as-a-service`, `MaasTenantConfig/default-tenant`, and the MaaS API are Ready. The generated API database user required `USAGE, CREATE` on the new database's `public` schema for migrations.
- The read-only preflight returns `ready-for-candidate-configuration`. A separate candidate namespace now publishes the existing Granite 3.2 8B Tools backend without creating another model workload. Its `MaaSModelRef` is Ready, its subscription is Active, and its authorization policy is restricted to one dedicated service identity.
- Candidate discovery returned only `granite-3-2-8b-tools-candidate`. Authorized inference returned HTTP 200 and the expected `candidate-maas-ok`; missing auth returned 401 and an invalid key returned 403. The short-lived client key exists only in an Arena Secret. A disposable key was revoked and denied, a separate one-minute key was denied after expiry, and a deterministic inference increased the candidate's Limitador counters by one call and 23 authorized hits, matching the model's 23-token response usage. The installed gateway returned 403 for revoked and expired keys rather than the 401 documented for the MaaS API; no denied request was authorized. The exact evidence is in `evidence/runs/catalog-intake-hybrid-fraud/arena-maas-candidate-model-green-20260922.json`.
- MaaS reaches the unchanged Granite service through its existing TLS OpenShift Route. A candidate-only DestinationRule in the gateway namespace trusts Arena's private ingress CA for that exact host; certificate verification remains enabled. No global trust or insecure-skip-verification setting was added.
- This remains `release_eligible: false`. Candidate-scoped expiration, revocation, and basic usage accounting are now proven. Launchpad seat-key issuance/revocation, source-bound live rendering, the full participant journey, and complete reclaim still require evidence.
- No cluster restart was performed. Existing Launchpad model endpoints and lab routes were not changed. ClusterOperator `console` remains Degraded due to a pre-existing expired custom TLS certificate; it is Available and that separate issue was not modified here.

## Historical read-only baseline before bootstrap

- Arena is OpenShift 4.22.3 with Red Hat OpenShift AI Operator 3.5.1. `default-dsc` has KServe `Managed` but `modelsAsService` **`Removed`**.
- The `maas-controller` Deployment and `maas-default-gateway` object exist. The older `Tenant/default-tenant` is `Failed`; neither a functioning MaaS API nor a key-enforcing model path has been demonstrated.
- User Workload Monitoring is enabled. The gateway uses a GatewayClass backed by `openshift.io/gateway-controller/v1`, but its required MaaS ownership/TLS-bootstrap annotations are absent.
- Authorino Operator 0.16.0 is installed, but no Authorino instance exists. No Kuadrant CRD/instance or Red Hat Connectivity Link Subscription exists.
- Arena's ready `redhat-operators` CatalogSource does **not** advertise `rhcl-operator`. Only community `kuadrant-operator` is visible. Do not substitute the community package for a supported Red Hat Connectivity Link install.
- `MaasTenantConfig` is not registered. OpenShift AI 3.5 uses its status to resolve the infrastructure namespace for `maas-db-config`; the older failed Tenant's message naming `redhat-ods-applications` must not be used as a Secret placement instruction.
- The existing Granite 8B deployment is a bare vLLM Deployment, not a `LLMInferenceService`. Its direct Service returns HTTP 200 for absent and invalid bearer tokens. It must remain unchanged until a separate governed path has passed negative tests.

## Dependency and execution order

1. Cluster subscription/catalog owner: confirm Arena's Red Hat Connectivity Link entitlement and make the supported `rhcl-operator` 1.4.1+ package available from `redhat-operators`; inspect version, install mode, and dependencies before applying a Subscription. The OpenShift AI 3.5 integration calls for the operator in `openshift-operators` and a ready Kuadrant CR in `kuadrant-system`. Resolve any discrepancy with generic Connectivity Link installation examples in favor of the OpenShift AI integration requirements.
2. Establish a ready Kuadrant and Authorino instance. Configure service-serving TLS for Authorino and verify the gateway's required annotations and TLS chain. Do not attach an AuthPolicy to any existing Launchpad or direct-vLLM route.
3. Provide a dedicated PostgreSQL 14+ instance for MaaS key lifecycle data, with an explicit backup, recovery, storage, and access policy. Do not reuse Launchpad's database or the existing `sas-ram-db` PostgresCluster. After the 3.5 `MaasTenantConfig` reports its `status.infraNamespace`, create `maas-db-config` with `DB_CONNECTION_URL` **in that namespace** through the approved secret-delivery path. Keep credentials out of Git, terminal history, and evidence.
4. Enable `modelsAsService` in the DataScienceCluster only after those dependencies are ready. Verify the Tenant Ready condition and the MaaS API Deployment in the resolved infrastructure namespace. An existing Gateway object or running controller alone is not a GREEN result.
5. Decide and validate a supported way to publish the existing Granite backend without a second full-size model deployment or a live route cutover. The installed `MaaSModelRef` allows `LLMInferenceService` or `ExternalModel`; a bare Deployment cannot be referenced directly. Keep external-model technology-preview status and support scope explicit if that route is considered.
6. Create a candidate-only model reference, subscription, and authorization policy. Prove missing/invalid/revoked key denial, valid one-seat access, model restriction, usage accounting, and direct-path isolation from a disposable namespace. Only then integrate Launchpad's key issuance/revocation and rerun the entire seat lifecycle, including cleanup and zero residue.

Rollback boundary: each stage is isolated from the current direct inference route. Stop on any failed prerequisite or readiness check; do not repoint current `config/clusters.yaml` endpoints, restart model serving, or activate a catalog item as part of bootstrap. If a newly created shared component must be rolled back, identify its exact ownership and dependents first; never delete the existing `maas-default-gateway`, DataScienceCluster, or older Tenant merely to clear a RED result.

Read-only check:

```bash
.venv/bin/python scripts/preflight_hybrid_fraud_maas.py --kubeconfig /Users/jkershaw/Documents/launchpad/.arena-kubeconfig
```

Sources: [OpenShift AI 3.5 MaaS platform and database prerequisites](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/govern_llm_access_with_models-as-a-service/deploy-and-manage-models-as-a-service); [Red Hat Connectivity Link 1.4 installation and supported configurations](https://docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/install_connectivity_link/rhcl-install-on-ocp).
