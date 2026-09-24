# Embedded OpenShift Console

This deployment enables the supported Red Hat Showroom experience in which the
OpenShift Console remains inside the `OpenShift Console` Showroom tab.

It uses the pinned `agnosticd.showroom.ocp4_workload_ocp_console_embed` role to:

- remove `X-Frame-Options` from the selected cluster's ingress responses;
- enforce an explicit `frame-ancestors` allowlist;
- convert and continuously reconcile the OpenShift OAuth route to re-encrypt
  TLS so the router can apply the response-header policy.

This is intentionally a cluster-admin operation. It changes the selected
cluster's default IngressController and OAuth route and rolls the default
router. Always pass the intended cluster's kubeconfig and ingress domain
explicitly; the playbook fails closed when the domain is absent.

```sh
ansible-galaxy collection install -r deploy/console-embed/requirements.yml
KUBECONFIG="$TARGET_CLUSTER_KUBECONFIG" \
OPENSHIFT_INGRESS_DOMAIN="apps.target-cluster.example.com" \
ansible-playbook \
  deploy/console-embed/playbook.yml \
  -e '{"public_lab_frame_origins":["https://public-labs.example.com"]}'
```

Every temporary tunnel hostname must be explicitly supplied. Permanent public
access should use the stable public labs domain so the allowlist does not need
to change for each pilot.

Validate both Console and OAuth responses after the router rollout. Neither may
return `X-Frame-Options`, and the enforced `Content-Security-Policy` must include
the exact Showroom origin.

For rollback, run the same playbook with `ACTION=destroy`, then verify the OAuth
route and default router have returned to their pre-embed configuration.
