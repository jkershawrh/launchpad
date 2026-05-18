from __future__ import annotations

import json
import subprocess
from typing import List

import httpx

from app.domain.enums import ValidationResultStatus
from app.domain.models import LabSession, ValidationResult


class OpenShiftValidationAdapter:
    def validate(self, session: LabSession) -> List[ValidationResult]:
        results: List[ValidationResult] = []
        namespace = session.namespace

        if not namespace:
            results.append(ValidationResult(
                session_id=session.session_id,
                check_name="namespace-exists",
                result=ValidationResultStatus.FAIL,
                message="No namespace set on session",
            ))
            return results

        results.extend(self._check_pod_status(session.session_id, namespace))

        routes = session.resources.get("routes", {})
        for route_name, route_url in routes.items():
            results.append(
                self._check_route_accessible(session.session_id, route_name, route_url)
            )

        return results

    def _check_pod_status(self, session_id: str, namespace: str) -> List[ValidationResult]:
        results: List[ValidationResult] = []
        try:
            proc = subprocess.run(
                ["oc", "get", "pods", "-n", namespace, "-o", "json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0:
                results.append(ValidationResult(
                    session_id=session_id,
                    check_name="pod-status",
                    result=ValidationResultStatus.FAIL,
                    message=f"Failed to query pods: {proc.stderr}",
                    evidence=proc.stderr,
                ))
                return results

            pod_data = json.loads(proc.stdout)
            pods = pod_data.get("items", [])

            if not pods:
                results.append(ValidationResult(
                    session_id=session_id,
                    check_name="pod-status",
                    result=ValidationResultStatus.FAIL,
                    message=f"No pods found in namespace {namespace}",
                ))
                return results

            for pod in pods:
                pod_name = pod["metadata"]["name"]
                phase = pod.get("status", {}).get("phase", "Unknown")
                container_statuses = pod.get("status", {}).get("containerStatuses", [])

                all_ready = all(
                    cs.get("ready", False) for cs in container_statuses
                ) if container_statuses else False

                if phase == "Running" and all_ready:
                    status = ValidationResultStatus.PASS
                    message = f"Pod {pod_name} is running and all containers ready"
                elif phase == "Running":
                    status = ValidationResultStatus.WARN
                    message = f"Pod {pod_name} is running but not all containers ready"
                else:
                    status = ValidationResultStatus.FAIL
                    message = f"Pod {pod_name} is in phase {phase}"

                results.append(ValidationResult(
                    session_id=session_id,
                    check_name=f"pod-{pod_name}",
                    result=status,
                    message=message,
                    evidence=f"phase={phase} ready={all_ready}",
                ))

        except subprocess.TimeoutExpired:
            results.append(ValidationResult(
                session_id=session_id,
                check_name="pod-status",
                result=ValidationResultStatus.FAIL,
                message="Timed out querying pod status",
            ))
        except Exception as e:
            results.append(ValidationResult(
                session_id=session_id,
                check_name="pod-status",
                result=ValidationResultStatus.FAIL,
                message=f"Error checking pods: {e}",
                evidence=str(e),
            ))

        return results

    def _check_route_accessible(
        self,
        session_id: str,
        route_name: str,
        route_url: str,
    ) -> ValidationResult:
        try:
            resp = httpx.get(route_url, timeout=10, follow_redirects=True, verify=False)
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
