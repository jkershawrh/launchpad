#!/usr/bin/env python3
"""Certify an Agent 201 workshop through Launchpad's persisted cluster client.

This driver is intentionally executed inside the Launchpad backend pod.  It
does not accept or load a local cluster credential: the workshop's persisted
``cluster_ref`` is checked against ``--cluster-id`` before the backend creates
the remote Kubernetes client.  Participant commands execute in each
Showroom terminal, which is the same namespace-scoped path used by the lab.

Only booleans, timings, object identifiers, and failure categories are emitted.
Model keys and other runtime credentials remain inside the participant pod.
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import json
import shlex
import sys
import time
import uuid
import warnings
from dataclasses import dataclass
from typing import Any

from kubernetes import client
from kubernetes.client.exceptions import ApiException

from app.api.deps import provisioning_service as service


warnings.filterwarnings("ignore", message="Unverified HTTPS request")


CONTENT_BASE = (
    "https://raw.githubusercontent.com/rhpds/launchpad/"
    "intel-guided-content-v1.0.13/content-intel-xeon6-agent-201/manifests"
)
EXPECTED_TOOLS = {
    "intel_hardware_lookup",
    "openshift_capabilities",
    "reference_architectures",
}


@dataclass(frozen=True)
class SeatTarget:
    seat_number: int
    session_id: str
    namespace: str
    terminal_image: str


class SeatProofError(RuntimeError):
    def __init__(self, stage: str) -> None:
        super().__init__(stage)
        self.stage = stage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workshop-id", required=True)
    parser.add_argument("--cluster-id", required=True)
    parser.add_argument("--setup-concurrency", type=int, default=5)
    parser.add_argument("--journey-concurrency", type=int, default=25)
    return parser.parse_args()


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _condition_ready(pod: Any) -> bool:
    return any(
        condition.type == "Ready" and condition.status == "True"
        for condition in (pod.status.conditions or [])
    )


def _terminal_image(clients: Any, namespace: str) -> str:
    pods = clients.core.list_namespaced_pod(
        namespace,
        label_selector="app=showroom",
    ).items
    if not pods:
        pods = clients.core.list_namespaced_pod(namespace).items
    candidates = [
        pod
        for pod in pods
        if pod.metadata.name.startswith("showroom-")
        and _condition_ready(pod)
        and any(container.name == "terminal" for container in pod.spec.containers)
    ]
    if len(candidates) != 1:
        raise RuntimeError("terminal-pod-not-uniquely-ready")
    return next(
        container.image
        for container in candidates[0].spec.containers
        if container.name == "terminal"
    )


def _load_targets(args: argparse.Namespace, clients: Any) -> list[SeatTarget]:
    workshop = service.get_workshop(args.workshop_id)
    if not workshop:
        raise RuntimeError("workshop-not-found")
    if workshop.cluster_ref != args.cluster_id:
        raise RuntimeError("workshop-cluster-mismatch")
    if workshop.status.value != "ready":
        raise RuntimeError("workshop-not-ready")
    if len(workshop.seats) != workshop.num_users:
        raise RuntimeError("workshop-seat-count-mismatch")

    targets: list[SeatTarget] = []
    for seat in sorted(workshop.seats, key=lambda item: item.seat_number):
        if seat.status.value != "ready" or not seat.session_id:
            raise RuntimeError("workshop-seat-not-ready")
        session = service.get_session(seat.session_id)
        if not session or session.status.value != "ready" or not session.namespace:
            raise RuntimeError("workshop-session-not-ready")
        if session.cluster_ref != args.cluster_id:
            raise RuntimeError("session-cluster-mismatch")
        namespace = clients.core.read_namespace(session.namespace)
        labels = namespace.metadata.labels or {}
        if labels.get("launchpad.redhat.com/cluster-id") != args.cluster_id:
            raise RuntimeError("namespace-cluster-label-mismatch")
        targets.append(
            SeatTarget(
                seat_number=seat.seat_number,
                session_id=session.session_id,
                namespace=session.namespace,
                terminal_image=_terminal_image(clients, session.namespace),
            )
        )
    return targets


def _run_participant_pod(
    clients: Any,
    target: SeatTarget,
    workshop_id: str,
    phase: str,
    script: str,
) -> dict[str, Any]:
    """Run a proof command as the existing seat-scoped Showroom identity.

    The remote provisioner deliberately cannot exec into participant pods.
    A short-lived pod using the existing ``showroom`` service account proves
    the participant path without broadening that infrastructure credential.
    """
    pod_name = f"lp-agent201-{phase[:1]}-{target.seat_number}-{uuid.uuid4().hex[:6]}"
    labels = {
        "app.kubernetes.io/managed-by": "launchpad",
        "app.kubernetes.io/component": "certification",
        "launchpad.redhat.com/workshop-id": workshop_id,
        "launchpad.redhat.com/session-id": target.session_id,
        "launchpad.redhat.com/certification-phase": phase,
    }
    pod = client.V1Pod(
        metadata=client.V1ObjectMeta(
            name=pod_name,
            namespace=target.namespace,
            labels=labels,
        ),
        spec=client.V1PodSpec(
            restart_policy="Never",
            service_account_name="showroom",
            active_deadline_seconds=390,
            termination_grace_period_seconds=5,
            containers=[
                client.V1Container(
                    name="certifier",
                    image=target.terminal_image,
                    command=["bash", "-lc", script],
                    env=[client.V1EnvVar(name="NAMESPACE", value=target.namespace)],
                    env_from=[
                        client.V1EnvFromSource(
                            secret_ref=client.V1SecretEnvSource(
                                name="launchpad-participant-runtime"
                            )
                        )
                    ],
                    resources=client.V1ResourceRequirements(
                        requests={"cpu": "10m", "memory": "32Mi"},
                        limits={"cpu": "250m", "memory": "256Mi"},
                    ),
                    security_context=client.V1SecurityContext(
                        allow_privilege_escalation=False,
                        capabilities=client.V1Capabilities(drop=["ALL"]),
                    ),
                )
            ],
        ),
    )
    clients.core.create_namespaced_pod(target.namespace, body=pod)
    deadline = time.monotonic() + 390
    try:
        while time.monotonic() < deadline:
            current = clients.core.read_namespaced_pod(pod_name, target.namespace)
            if current.status.phase in {"Succeeded", "Failed"}:
                output = clients.core.read_namespaced_pod_log(
                    pod_name,
                    target.namespace,
                    container="certifier",
                )
                if current.status.phase != "Succeeded":
                    try:
                        failed_result = _parse_last_json(output)
                    except RuntimeError:
                        raise SeatProofError("participant_proof_pod")
                    raise SeatProofError(
                        str(failed_result.get("failure_stage", "participant_proof_pod"))
                    )
                return _parse_last_json(output)
            time.sleep(2)
        raise TimeoutError("participant-proof-pod-timeout")
    finally:
        try:
            clients.core.delete_namespaced_pod(
                pod_name,
                target.namespace,
                grace_period_seconds=0,
                propagation_policy="Background",
            )
        except ApiException as exc:
            if exc.status != 404:
                log(
                    f"{phase}: seat {target.seat_number} transient pod cleanup failed"
                )


def _setup_script() -> str:
    manifests = (
        "advisor-prompt-configmap.yaml",
        "solution-tools.yaml",
        "solution-agent.yaml",
        "solution-ui.yaml",
    )
    apply_commands = "\n".join(
        f'oc apply -n "$NAMESPACE" -f {CONTENT_BASE}/{manifest} >/dev/null'
        for manifest in manifests
    )
    return f"""
set -euo pipefail
test -n "$MAAS_ENDPOINT"
test -n "$MAAS_API_KEY"
test -n "$MAAS_MODEL"
oc create configmap racmaas-connection -n "$NAMESPACE" \\
  --from-literal="api-base=$MAAS_ENDPOINT" \\
  --dry-run=client -o yaml | oc apply -n "$NAMESPACE" -f - >/dev/null
oc create secret generic litellm-api-key -n "$NAMESPACE" \\
  --from-literal="api-key=$MAAS_API_KEY" \\
  --dry-run=client -o yaml | oc apply -n "$NAMESPACE" -f - >/dev/null
{apply_commands}
oc set env -n "$NAMESPACE" deployment/solution-agent --containers=solution-agent \\
  "ADVISOR_MODEL=$MAAS_MODEL" >/dev/null
oc rollout status -n "$NAMESPACE" deployment/solution-agent --timeout=330s >/dev/null
oc rollout status -n "$NAMESPACE" deployment/solution-ui --timeout=330s >/dev/null
printf '{{"setup":true}}\\n'
"""


def _journey_script(cross_namespace: str) -> str:
    query = (
        "A retail chain needs real-time inventory prediction across 500 stores "
        "on an on-premises OpenShift platform. Recommend a sourced Intel and "
        "Red Hat architecture with a migration path."
    )
    expected_tools = json.dumps(sorted(EXPECTED_TOOLS), separators=(",", ":"))
    request = json.dumps({"query": query}, separators=(",", ":"))
    safe_cross_namespace = shlex.quote(cross_namespace)
    return f"""
set -uo pipefail
fail() {{
  jq -nc --arg stage "$1" '{{passed:false,"failure_stage":$stage}}'
  exit 1
}}
started=$(date +%s)
tools_host=$(oc get route tools -n "$NAMESPACE" -o jsonpath='{{.spec.host}}') || fail route_discovery
agent_host=$(oc get route agent -n "$NAMESPACE" -o jsonpath='{{.spec.host}}') || fail route_discovery
app_host=$(oc get route app -n "$NAMESPACE" -o jsonpath='{{.spec.host}}') || fail route_discovery
test -n "$tools_host" -a -n "$agent_host" -a -n "$app_host" || fail route_discovery
tools_url="https://$tools_host"
agent_url="https://$agent_host"
app_url="https://$app_host"
tools_http=$(curl -ksS --max-time 60 -o /dev/null -w '%{{http_code}}' "$tools_url/health") || fail tools_health
agent_http=$(curl -ksS --max-time 60 -o /dev/null -w '%{{http_code}}' "$agent_url/health") || fail agent_health
app_http=$(curl -ksS --max-time 60 -o /dev/null -w '%{{http_code}}' "$app_url/") || fail app_health
test "$tools_http" = 200 || fail tools_health
test "$agent_http" = 200 || fail agent_health
test "$app_http" = 200 || fail app_health
tools_file=$(mktemp)
answer_file=$(mktemp)
trap 'rm -f "$tools_file" "$answer_file"' EXIT
curl -ksSf --max-time 60 -X POST "$tools_url/mcp" \\
  -H 'Content-Type: application/json' \\
  --data '{{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{{}}}}' \\
  -o "$tools_file" || fail tools_contract
jq -e --argjson expected '{expected_tools}' \\
  '[.result.tools[].name] | sort == ($expected | sort)' "$tools_file" >/dev/null \\
  || fail tools_contract
answer_http=$(curl -ksS --max-time 330 -o "$answer_file" -w '%{{http_code}}' \\
  -X POST "$agent_url/api/v1/advise" \\
  -H 'Content-Type: application/json' \\
  --data '{request}') || fail model_request
test "$answer_http" = 200 || fail model_request
jq -e '
  (.brief | type == "string" and length > 100)
  and (.requirements != null)
  and (.hardware_options != null)
  and (.platform_capabilities != null)
  and (.architecture != null)
  and ([.inference_log[] | select(.error != null)] | length == 0)
  and ([.inference_log[] | select(.tool == "intel_hardware_lookup")] | length >= 1)
  and ([.inference_log[] | select(.tool == "openshift_capabilities")] | length >= 1)
  and ([.inference_log[] | select(.tool == "reference_architectures")] | length >= 1)
' "$answer_file" >/dev/null || fail response_contract
own_namespace_edit=$(oc auth can-i create deployments.apps -n "$NAMESPACE")
cross_namespace_read=$(oc auth can-i get pods -n {safe_cross_namespace})
node_list=$(oc auth can-i list nodes)
test "$own_namespace_edit" = yes || fail own_namespace_authorization
test "$cross_namespace_read" = no || fail cross_namespace_authorization
test "$node_list" = no || fail cluster_scope_authorization
elapsed=$(($(date +%s) - started))
jq -nc \\
  --argjson duration "$elapsed" \\
  --argjson tools_http "$tools_http" \\
  --argjson agent_http "$agent_http" \\
  --argjson app_http "$app_http" \\
  '{{passed:true,duration_seconds:$duration,tools_http:$tools_http,agent_http:$agent_http,app_http:$app_http,tools_exact:true,agent_response_valid:true,own_namespace_edit:true,cross_namespace_read_denied:true,node_list_denied:true}}'
"""


def _parse_last_json(output: str) -> dict[str, Any]:
    if isinstance(output, bytes):
        output = output.decode("utf-8", "replace")
    elif output.startswith(("b'", 'b"')):
        try:
            represented = ast.literal_eval(output)
            if isinstance(represented, bytes):
                output = represented.decode("utf-8", "replace")
        except (SyntaxError, ValueError):
            pass
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError("terminal-result-missing")


def _run_parallel(
    *,
    phase: str,
    targets: list[SeatTarget],
    concurrency: int,
    operation: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {pool.submit(operation, target): target for target in targets}
        for future in concurrent.futures.as_completed(futures):
            target = futures[future]
            try:
                result = future.result()
                results.append({"seat_number": target.seat_number, **result})
                log(f"{phase}: seat {target.seat_number} passed")
            except Exception as exc:  # Evidence intentionally excludes exception text.
                failure = {
                    "seat_number": target.seat_number,
                    "category": type(exc).__name__,
                }
                if isinstance(exc, SeatProofError):
                    failure["failure_stage"] = exc.stage
                failures.append(failure)
                log(f"{phase}: seat {target.seat_number} failed ({type(exc).__name__})")
    return sorted(results, key=lambda item: item["seat_number"]), sorted(
        failures, key=lambda item: item["seat_number"]
    )


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    evidence: dict[str, Any] = {
        "workshop_id": args.workshop_id,
        "cluster_id": args.cluster_id,
        "contains_plaintext_credentials": False,
        "status": "failed",
    }
    try:
        clients = service._target_clients(args.cluster_id)
        if clients is None:
            raise RuntimeError("target-client-unavailable")
        targets = _load_targets(args, clients)
        if len(targets) < 2:
            raise RuntimeError("cross-namespace-proof-requires-two-seats")
        evidence["seat_count"] = len(targets)

        setup_results, setup_failures = _run_parallel(
            phase="setup",
            targets=targets,
            concurrency=args.setup_concurrency,
            operation=lambda target: _run_participant_pod(
                clients,
                target,
                args.workshop_id,
                "setup",
                _setup_script(),
            ),
        )
        evidence["setup"] = {
            "passed": len(setup_results),
            "failed": setup_failures,
        }
        if setup_failures:
            raise RuntimeError("seat-setup-failed")

        namespaces = [target.namespace for target in targets]

        def journey(target: SeatTarget) -> dict[str, Any]:
            cross_namespace = next(
                namespace for namespace in namespaces if namespace != target.namespace
            )
            return _run_participant_pod(
                clients,
                target,
                args.workshop_id,
                "journey",
                _journey_script(cross_namespace),
            )

        journey_results, journey_failures = _run_parallel(
            phase="journey",
            targets=targets,
            concurrency=args.journey_concurrency,
            operation=journey,
        )
        evidence["journeys"] = {
            "passed": len(journey_results),
            "failed": journey_failures,
            "results": journey_results,
        }
        evidence["status"] = "passed" if not journey_failures else "failed"
    except Exception as exc:  # Evidence intentionally excludes exception text.
        evidence["failure_category"] = type(exc).__name__
        log(f"certification failed ({type(exc).__name__})")
    evidence["duration_seconds"] = round(time.monotonic() - started, 3)
    print(json.dumps(evidence, sort_keys=True))
    return 0 if evidence["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
