from __future__ import annotations

from typing import List
import time

import httpx

try:
    from kubernetes import client, config
    from kubernetes.client.exceptions import ApiException

    HAS_KUBERNETES = True
except ImportError:  # pragma: no cover
    HAS_KUBERNETES = False

from app.domain.enums import ValidationResultStatus
from app.domain.models import LabSession, ValidationResult


class OpenShiftValidationAdapter:
    def __init__(self, *, clients=None) -> None:
        if not HAS_KUBERNETES:
            raise ValueError(
                "The 'kubernetes' Python package is required for OpenShiftValidationAdapter. "
                "Install it with: pip install kubernetes"
            )

        if clients is None:
          try:
            config.load_incluster_config()
          except config.ConfigException:
            try:
                config.load_kube_config()
            except config.ConfigException as exc:
                raise ValueError(
                    f"Unable to load Kubernetes configuration "
                    f"(tried in-cluster and kubeconfig): {exc}"
                ) from exc

          self._core_v1 = client.CoreV1Api()
        else:
          self._core_v1 = clients.core
        self._validation_attempts = 13
        self._validation_interval = 5
        self._sleep = time.sleep

    def validate(self, session: LabSession) -> List[ValidationResult]:
        results: List[ValidationResult] = []
        for attempt in range(self._validation_attempts):
            results = self._validate_once(session)
            transient = any(
                result.result == ValidationResultStatus.FAIL
                and (
                    "phase Pending" in result.message
                    or "returned 502" in result.message
                    or "returned 503" in result.message
                    or "returned 504" in result.message
                )
                for result in results
            )
            if not transient or attempt == self._validation_attempts - 1:
                return results
            self._sleep(self._validation_interval)
        return results

    def _validate_once(self, session: LabSession) -> List[ValidationResult]:
        results: List[ValidationResult] = []
        namespace = session.namespace

        if not namespace:
            results.append(
                ValidationResult(
                    session_id=session.session_id,
                    check_name="namespace-exists",
                    result=ValidationResultStatus.FAIL,
                    message="No namespace set on session",
                )
            )
            return results

        results.extend(self._check_pod_status(session.session_id, namespace))

        routes = session.resources.get("routes", {})
        for route_name, route_url in routes.items():
            results.append(
                self._check_route_accessible(session.session_id, route_name, route_url)
            )

        return results

    def _check_pod_status(
        self, session_id: str, namespace: str
    ) -> List[ValidationResult]:
        results: List[ValidationResult] = []
        try:
            pod_list = self._core_v1.list_namespaced_pod(namespace)
            pods = pod_list.items or []

            if not pods:
                results.append(
                    ValidationResult(
                        session_id=session_id,
                        check_name="pod-status",
                        result=ValidationResultStatus.FAIL,
                        message=f"No pods found in namespace {namespace}",
                    )
                )
                return results

            for pod in pods:
                pod_name = pod.metadata.name
                phase = pod.status.phase if pod.status else "Unknown"
                container_statuses = (
                    pod.status.container_statuses if pod.status else None
                ) or []

                all_ready = (
                    all(cs.ready for cs in container_statuses)
                    if container_statuses
                    else False
                )

                if phase == "Running" and all_ready:
                    status = ValidationResultStatus.PASS
                    message = f"Pod {pod_name} is running and all containers ready"
                elif phase == "Running":
                    status = ValidationResultStatus.WARN
                    message = (
                        f"Pod {pod_name} is running but not all containers ready"
                    )
                else:
                    status = ValidationResultStatus.FAIL
                    message = f"Pod {pod_name} is in phase {phase}"

                results.append(
                    ValidationResult(
                        session_id=session_id,
                        check_name=f"pod-{pod_name}",
                        result=status,
                        message=message,
                        evidence=f"phase={phase} ready={all_ready}",
                    )
                )

        except ApiException as exc:
            results.append(
                ValidationResult(
                    session_id=session_id,
                    check_name="pod-status",
                    result=ValidationResultStatus.FAIL,
                    message=f"Failed to query pods: {exc.status} {exc.reason}",
                    evidence=f"{exc.status} {exc.reason}",
                )
            )
        except Exception as e:
            results.append(
                ValidationResult(
                    session_id=session_id,
                    check_name="pod-status",
                    result=ValidationResultStatus.FAIL,
                    message=f"Error checking pods: {e}",
                    evidence=str(e),
                )
            )

        return results

    def _check_route_accessible(
        self,
        session_id: str,
        route_name: str,
        route_url: str,
    ) -> ValidationResult:
        try:
            resp = httpx.get(
                route_url, timeout=10, follow_redirects=True, verify=False
            )
            if resp.status_code < 500:
                return ValidationResult(
                    session_id=session_id,
                    check_name=f"route-{route_name}",
                    result=ValidationResultStatus.PASS,
                    message=f"Route {route_name} ({route_url}) returned {resp.status_code}",
                    evidence=f"HTTP {resp.status_code}",
                )
            else:
                return ValidationResult(
                    session_id=session_id,
                    check_name=f"route-{route_name}",
                    result=ValidationResultStatus.FAIL,
                    message=f"Route {route_name} ({route_url}) returned {resp.status_code}",
                    evidence=f"HTTP {resp.status_code}",
                )
        except httpx.RequestError as e:
            return ValidationResult(
                session_id=session_id,
                check_name=f"route-{route_name}",
                result=ValidationResultStatus.FAIL,
                message=f"Route {route_name} ({route_url}) unreachable: {e}",
                evidence=str(e),
            )
