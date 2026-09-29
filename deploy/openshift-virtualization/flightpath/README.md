# Flightpath OpenShift Virtualization

These manifests install the supported Red Hat OpenShift Virtualization operator
from the `stable` channel and create the cluster `HyperConverged` instance.

Apply them only to the Flightpath cluster, in order:

```bash
oc --context default/api-flightpath-fm2aihpcsed-com:6443/kube:admin \
  --server https://api.flightpath.fm2aihpcsed.com:6443 \
  apply -f deploy/openshift-virtualization/flightpath/operator.yaml

# Wait for the installed CSV in openshift-cnv to report Succeeded, then:
oc --context default/api-flightpath-fm2aihpcsed-com:6443/kube:admin \
  --server https://api.flightpath.fm2aihpcsed.com:6443 \
  apply -f deploy/openshift-virtualization/flightpath/hyperconverged.yaml
```

Do not infer lab readiness from the operator alone. Certification must also
prove that the `HyperConverged` resource is Available, VM/VMI APIs are served,
the virtualization control-plane and node components are healthy, a VM can run
on every eligible worker, and cleanup leaves zero residue.
