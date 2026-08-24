"""Capacity and reservation adapter for direct OpenShift provisioning."""
from __future__ import annotations

import threading
from typing import Any, Dict

try:
    from kubernetes import client, config

    HAS_KUBERNETES = True
except ImportError:  # pragma: no cover
    HAS_KUBERNETES = False


class OpenShiftPoolAdapter:
    """Represent on-demand namespace capacity in the current OpenShift cluster.

    Direct OpenShift mode does not claim a pre-created sandbox. Capacity means
    the backend service account is currently authorized to create namespaces;
    Kubernetes scheduling and quotas remain the final admission controls.
    """

    def __init__(self) -> None:
        if not HAS_KUBERNETES:
            raise ValueError(
                "The 'kubernetes' Python package is required for OpenShiftPoolAdapter."
            )

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

        self._authorization = client.AuthorizationV1Api()
        self._reservations: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def check_capacity(self, hardware_profile: str, quota_profile: str) -> bool:
        review = client.V1SelfSubjectAccessReview(
            spec=client.V1SelfSubjectAccessReviewSpec(
                resource_attributes=client.V1ResourceAttributes(
                    group="",
                    resource="namespaces",
                    verb="create",
                )
            )
        )
        result = self._authorization.create_self_subject_access_review(review)
        return bool(result.status and result.status.allowed)

    def reserve(
        self,
        session_id: str,
        hardware_profile: str,
        quota_profile: str,
    ) -> Dict[str, Any]:
        reservation = {
            "session_id": session_id,
            "hardware_profile": hardware_profile,
            "quota_profile": quota_profile,
            "status": "reserved",
            "provider": "openshift",
        }
        with self._lock:
            self._reservations[session_id] = reservation
        return dict(reservation)

    def release(self, session_id: str) -> bool:
        with self._lock:
            return self._reservations.pop(session_id, None) is not None

    def report_allocation(self) -> Dict[str, Any]:
        with self._lock:
            reservations = [dict(value) for value in self._reservations.values()]
        return {
            "total_reservations": len(reservations),
            "reservations": reservations,
            "provider": "openshift",
        }
