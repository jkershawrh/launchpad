# Your first governed AI workload

You have been given an open OpenShift sandbox, not a scripted application.
Your first mission is intentionally small: prove your project boundary, deploy
one tiny web workload, make one honest completion with the managed
`granite-2b-cpu` model assigned to this seat when it is available, capture
evidence, and remove what you created. The model is centrally served; this
sandbox does not deploy or claim a local model server. After that, the
namespace remains yours for open exploration.

Use only fictional or sanitized information. The helper never prints or stores
your model credential.

## Show

See the environment Launchpad prepared for this seat:

```bash
launchpad-guided-start show
oc whoami
oc project -q
```

Open the OpenShift Console alongside the terminal. You should see one sandbox
Deployment in only your assigned namespace.

## Learn

Prove the boundary before changing anything:

```bash
launchpad-guided-start learn
```

The result must say that you can edit your own namespace, cannot read the
Launchpad control namespace, and cannot list cluster Nodes. A warning that
Nodes are cluster scoped is normal; the authorization result must be `no`.

## Do

Create one small, labeled web workload using the already-pulled sandbox image:

```bash
launchpad-guided-start do
```

Inspect `guided-start` in the OpenShift Console. The helper creates one
Deployment, one Service, and one ConfigMap, waits for the pod, and verifies its
HTTP response from inside the pod. It does not expose a public Route.

## Prove

Capture namespace, workload, and inference evidence:

```bash
launchpad-guided-start prove
python3 -m json.tool guided-start-proof.json
```

When the Launchpad model endpoint, assigned model, and seat credential are
configured, the helper confirms that the assigned `granite-2b-cpu` identity is
advertised and makes one `/v1/chat/completions` request for that model only.
The proof records `live`, the returned model ID, token counts when reported,
and the short fictional response. If the assigned model is absent or inference
is unavailable, the proof says `unavailable` with a reason; it never chooses a
different advertised model, substitutes rehearsal output, or claims that a
model ran.

## Clean up

Remove only the resources created by this guided start and prove they are gone:

```bash
launchpad-guided-start cleanup
python3 -m json.tool guided-start-proof.json
```

The final cleanup status must be `complete`. Launchpad reclamation later
removes the entire namespace, persistent workspace, and short-lived model
credential. Your own files remain in the workspace until that reclaim occurs.

For a quick verification run, `launchpad-guided-start all` executes the full
path and finishes with cleanup. Then continue exploring with the IDE, terminal,
OpenShift Console, playbooks, and any namespace-scoped workloads you choose.
