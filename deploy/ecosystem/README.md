# Portable Launchpad ecosystem playbooks

These Ansible playbooks provide a thin, repeatable orchestration layer around
the repository's existing Kustomize overlays, remote-cluster RBAC, Launchpad
APIs, and certification runner. They do not reimplement provisioning and they
do not require AgnosticD for the internal Intel platform.

The controller runs locally and every OpenShift command receives an explicit
kubeconfig. The playbooks never change the workstation's current context,
store credentials in inventory, copy kubeadmin credentials, or fall back to a
different cluster.

## Files

- `inventory.example.yml`: local orchestration inventory;
- `group_vars/all.example.yml`: non-secret topology inputs;
- `playbooks/preflight.yml`: read-only control/execution-cluster gate;
- `playbooks/deploy-control-plane.yml`: server-side apply of an approved overlay;
- `playbooks/register-execution-cluster.yml`: apply remote RBAC, validate a
  pre-created least-privilege kubeconfig, and store the encrypted Secret;
- `playbooks/validate.yml`: API readiness and complete cluster preflight;
- `playbooks/reclaim-workshop.yml`: API-driven group reclaim plus target-cluster
  and Argo CD residue checks.

## Credential boundary

Create one least-privilege provisioner identity per execution cluster using
the reviewed manifests in `deploy/multicluster/`. Supply its kubeconfig as a
local protected file. Argo CD uses a separate identity and registration
manifest. Neither file belongs in Git or Ansible inventory. Use an external
secret manager or a protected CI secret-file mechanism for repeat runs.

The admin API key is read only from `LAUNCHPAD_ADMIN_API_KEY` at runtime.

## Run

Copy the examples to a location outside the repository, update only paths and
non-secret cluster metadata, then run:

```bash
ansible-playbook -i /secure/launchpad-inventory.yml \
  deploy/ecosystem/playbooks/preflight.yml

ansible-playbook -i /secure/launchpad-inventory.yml \
  deploy/ecosystem/playbooks/deploy-control-plane.yml

ansible-playbook -i /secure/launchpad-inventory.yml \
  deploy/ecosystem/playbooks/register-execution-cluster.yml \
  -e target_cluster_id=brutus

LAUNCHPAD_ADMIN_API_KEY='supplied-outside-git' \
ansible-playbook -i /secure/launchpad-inventory.yml \
  deploy/ecosystem/playbooks/validate.yml
```

Reclaim one order through Launchpad, not by deleting its namespace:

```bash
LAUNCHPAD_ADMIN_API_KEY='supplied-outside-git' \
ansible-playbook -i /secure/launchpad-inventory.yml \
  deploy/ecosystem/playbooks/reclaim-workshop.yml \
  -e workshop_id=<uuid> -e target_cluster_id=arena
```

The supplied target must equal the workshop's persisted `cluster_ref`; the
playbook asserts that fact before mutation and fails when any labeled namespace
or Argo CD Application remains.

## New cluster graduation

1. Run preflight without changing the cluster.
2. Create dedicated Launchpad and Argo identities with reviewed RBAC.
3. Register immutable images, ingress trust, storage, capabilities, and model routes.
4. Keep the target disabled in `config/clusters.yaml`.
5. Run one operator sandbox, one Showroom, then catalog-specific 1/5/25 proof.
6. Prove bulk reclaim and zero residue after every stage.
7. Publish the measured seat ceiling and enable only approved catalog/cluster pairs.

Public access and Flightpath promotion have separate certification and fencing
requirements. Registering an execution cluster does not certify either.
