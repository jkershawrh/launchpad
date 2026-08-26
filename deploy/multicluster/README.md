# Arena registration

Apply `arena-rbac.yaml` to Arena, create a bound service-account token, and
build a kubeconfig for that identity. Store it on Oberon without committing it:

```sh
oc -n partner-ai-launchpad create secret generic launchpad-arena-kubeconfig \
  --from-file=kubeconfig=/secure/path/arena-launchpad.kubeconfig
```

Register the same cluster credential in Oberon's Argo CD using its supported
cluster-secret workflow. The Argo destination server must match
`https://api.arena.fm2aihpcsed.com:6443` in `config/clusters.yaml`.

Never copy kubeadmin credentials into Launchpad or Git.

Apply `arena-argocd-rbac.yaml` separately for the central Argo CD registration.
The Argo identity has cluster-wide read access because its cache discovers
cluster resource kinds, while mutation remains limited to the resources used
by Showroom. Do not reuse the Argo credential for Launchpad provisioning.
