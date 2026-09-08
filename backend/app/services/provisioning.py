from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid as _uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional

from app.adapters.interfaces import ConstraintResult
from app.adapters.mock.branding import FileBrandingAdapter
from app.adapters.mock.catalog import MockCatalogAdapter
from app.adapters.mock.constraints import MockConstraintAdapter
from app.adapters.mock.observability import MockObservabilityAdapter
from app.adapters.mock.pool import MockPoolAdapter
from app.adapters.mock.provisioning import MockProvisioningAdapter
from app.adapters.mock.showback import MockShowbackAdapter
from app.adapters.mock.validation import MockValidationAdapter
from app.domain.access import ExposurePolicy
from app.domain.enums import (
    CatalogCategory,
    LabRequestStatus,
    Persistence,
    SessionStatus,
    WorkshopSeatStatus,
    WorkshopStatus,
)
from app.domain.lifecycle import transition
from app.domain.models import (
    LabRequest,
    LabSession,
    LifecycleEvent,
    ProvisioningPlan,
    ShowbackRecord,
    Workshop,
    WorkshopSeat,
)
from app.domain.reports import HandoffPackage, RepeatabilityReport, SecurityPlan
from app.integrations.event_publisher import publish_event as notify_stargate

logger = __import__("logging").getLogger("launchpad.provisioning")


def parse_ttl(value: str) -> timedelta:
    """Parse a positive integer TTL with seconds, minutes, hours, or days."""
    match = re.fullmatch(r"\s*(\d+)\s*([smhd])\s*", value, re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid TTL '{value}'; expected formats such as 10m, 4h, or 1d")
    amount = int(match.group(1))
    unit = match.group(2).lower()
    keyword = {
        "s": "seconds",
        "m": "minutes",
        "h": "hours",
        "d": "days",
    }[unit]
    return timedelta(**{keyword: amount})


class ProvisioningService:
    def __init__(
        self,
        catalog=None,
        pool=None,
        constraints=None,
        provisioner=None,
        validator=None,
        observability=None,
        showback=None,
        branding=None,
        cleanup=None,
        db_stores=None,
        placement=None,
        workload_classifier=None,
        feedback_tracker=None,
        brain=None,
        preflight=None,
        maas_key_broker=None,
        cluster_registry=None,
        cluster_client_factory=None,
    ):
        self.catalog = catalog or MockCatalogAdapter()
        self.pool = pool or MockPoolAdapter()
        self.constraints = constraints or MockConstraintAdapter()
        self.provisioner = provisioner or MockProvisioningAdapter()
        self.validator = validator or MockValidationAdapter()
        self.observability = observability or MockObservabilityAdapter()
        self.showback = showback or MockShowbackAdapter()
        self.branding = branding or FileBrandingAdapter()
        self.cleanup = cleanup
        self.db = db_stores
        self.placement = placement
        self.workload_classifier = workload_classifier
        self.feedback_tracker = feedback_tracker
        self.brain = brain
        self.preflight = preflight
        self.maas_key_broker = maas_key_broker
        self.cluster_registry = cluster_registry
        self.cluster_client_factory = cluster_client_factory

        mode = os.environ.get("LAUNCHPAD_MODE", "mock")
        if mode != "mock":
            if isinstance(self.pool, MockPoolAdapter):
                logger.warning("MockPoolAdapter used in %s mode — check adapter wiring in deps.py", mode)
            if isinstance(self.provisioner, MockProvisioningAdapter):
                logger.warning("MockProvisioningAdapter used in %s mode — check adapter wiring in deps.py", mode)

        self._requests: dict[str, LabRequest] = {}
        self._sessions: dict[str, LabSession] = {}
        self._plans: dict[str, ProvisioningPlan] = {}
        self._workshops: dict[str, Workshop] = {}
        self._workshop_idempotency: dict[tuple[str, str], tuple[str, str]] = {}
        self._workshop_provision_events: dict[str, threading.Event] = {}
        self._gw_locks: dict[str, threading.Lock] = {}
        self._load_from_db()

    def _load_from_db(self) -> None:
        if not self.db:
            return
        if hasattr(self.db, 'sessions'):
            for session in self.db.sessions.list_all():
                self._sessions[session.session_id] = session
        if hasattr(self.db, 'requests'):
            for request in self.db.requests.list_all():
                self._requests[request.request_id] = request
        if hasattr(self.db, 'workshops'):
            for workshop in self.db.workshops.list_all():
                self._workshops[workshop.workshop_id] = workshop
                if workshop.idempotency_key and workshop.order_fingerprint:
                    self._workshop_idempotency[
                        (workshop.tenant_id, workshop.idempotency_key)
                    ] = (workshop.order_fingerprint, workshop.workshop_id)
        self._cleanup_orphaned_sessions()

    def _cleanup_orphaned_sessions(self) -> None:
        active_statuses = {"ready", "active", "validating", "provisioning", "resetting"}
        for session in list(self._sessions.values()):
            if session.status.value in active_statuses and session.namespace:
                try:
                    if os.environ.get("LAUNCHPAD_MODE") == "openshift":
                        from kubernetes import client, config
                        try:
                            config.load_incluster_config()
                        except Exception:
                            config.load_kube_config()
                        core = (
                            self._target_clients(session.cluster_ref).core
                            if session.cluster_ref and self.cluster_client_factory
                            else client.CoreV1Api()
                        )
                        try:
                            core.read_namespace(session.namespace)
                        except client.exceptions.ApiException as e:
                            if e.status != 404:
                                logger.warning(
                                    "Namespace check failed for active session %s: %s",
                                    session.session_id,
                                    e,
                                )
                                continue
                            logger.info("Namespace %s gone, reclaiming orphaned session %s: %s", session.namespace, session.session_id, e)
                            event = LifecycleEvent(
                                from_status=session.status,
                                to_status=SessionStatus.RECLAIMED,
                                reason="orphaned — namespace no longer exists",
                            )
                            session = session.model_copy(
                                update={
                                    "status": SessionStatus.RECLAIMED,
                                    "completed_at": datetime.utcnow(),
                                    "lifecycle_events": session.lifecycle_events + [event],
                                }
                            )
                            session = self._scrub_credentials(session)
                            self._save_session(session)
                except Exception as e:
                    logger.warning("Failed to check orphaned session %s: %s", session.session_id, e)

        if os.environ.get("LAUNCHPAD_MODE") == "openshift":
            try:
                from app.services.resource_reconciliation import reconcile_resources
                report = reconcile_resources(self)
                logger.info("Resource reconciliation complete: %s", report)
            except Exception as exc:
                logger.warning("Resource reconciliation failed: %s", exc)

    def _target_clients(self, cluster_ref: Optional[str]):
        if not cluster_ref or not self.cluster_client_factory:
            return None
        # Enabled is a placement control, not a lifecycle kill switch. Once a
        # target is persisted, validation, reconciliation and cleanup must keep
        # using that exact cluster even if normal placement is disabled.
        return self.cluster_client_factory.clients(cluster_ref, allow_disabled=True)

    def _target_config(self, cluster_ref: str):
        """Resolve a persisted target without making it generally placeable."""
        return self.cluster_registry.inspect(cluster_ref)

    def _get_provisioner(self, catalog_item, cluster_ref: Optional[str] = None):
        from app.domain.enums import CatalogCategory

        mode = os.environ.get("LAUNCHPAD_MODE", "mock")
        if mode == "rhdp" and catalog_item.metadata.get("provisioner_mode") == "rhdp":
            from app.adapters.rhdp.provisioning import RHDPProvisioningAdapter
            return RHDPProvisioningAdapter()

        if catalog_item.category == CatalogCategory.OPEN_SANDBOX:
            mode = os.environ.get("LAUNCHPAD_MODE", "mock")
            if mode == "openshift":
                from app.adapters.openshift.sandbox_provisioning import OpenShiftSandboxProvisioner
                if cluster_ref and self.cluster_registry:
                    return OpenShiftSandboxProvisioner(
                        clients=self._target_clients(cluster_ref),
                        target=self._target_config(cluster_ref),
                    )
                return OpenShiftSandboxProvisioner()
            elif mode == "local":
                from app.adapters.local.sandbox_provisioner import LocalSandboxProvisioner
                return LocalSandboxProvisioner()
        if mode == "openshift" and cluster_ref and self.cluster_registry:
            from app.adapters.openshift.provisioning import OpenShiftProvisioningAdapter
            target = self._target_config(cluster_ref)
            clients = self._target_clients(cluster_ref)
            control_clients = self._target_clients(self._control_cluster_ref(cluster_ref))
            return OpenShiftProvisioningAdapter(
                clients=clients,
                target=target,
                argocd_custom_objects=control_clients.custom if control_clients else None,
                control_core=control_clients.core if control_clients else None,
            )
        return self.provisioner

    def _get_validator(self, cluster_ref: Optional[str]):
        if os.environ.get("LAUNCHPAD_MODE") == "openshift" and cluster_ref and self.cluster_client_factory:
            from app.adapters.openshift.validation import OpenShiftValidationAdapter
            return OpenShiftValidationAdapter(clients=self._target_clients(cluster_ref))
        return self.validator

    def _get_pool(self, cluster_ref: Optional[str]):
        if os.environ.get("LAUNCHPAD_MODE") == "openshift" and cluster_ref and self.cluster_client_factory:
            from app.adapters.openshift.pool import OpenShiftPoolAdapter
            return OpenShiftPoolAdapter(clients=self._target_clients(cluster_ref))
        return self.pool

    def _get_cleanup(self, cluster_ref: Optional[str]):
        if os.environ.get("LAUNCHPAD_MODE") == "openshift" and cluster_ref and self.cluster_client_factory:
            from app.adapters.openshift.cleanup import OpenShiftCleanupAdapter
            control_clients = self._target_clients(self._control_cluster_ref(cluster_ref))
            return OpenShiftCleanupAdapter(
                clients=self._target_clients(cluster_ref),
                argocd_custom_objects=control_clients.custom if control_clients else None,
            )
        return self.cleanup

    def _control_cluster_ref(self, target_cluster_ref: Optional[str]) -> str:
        """Resolve the cluster hosting Launchpad and its central Argo CD instance."""
        configured = os.environ.get("LAUNCHPAD_CONTROL_CLUSTER_REF", "").strip()
        if configured:
            return configured
        if self.cluster_registry:
            for target in self.cluster_registry.list_enabled():
                if target.local or "control-plane" in target.capabilities:
                    return target.cluster_id
        if target_cluster_ref:
            return target_cluster_ref
        return "oberon"

    def _select_target_cluster(
        self,
        request: LabRequest,
        catalog_item,
        *,
        allow_disabled_override: bool = False,
    ) -> Optional[str]:
        override = request.metadata.get("target_cluster")
        required_models = request.requested_models or (
            (catalog_item.metadata or {}).get("required_models", [])
        )
        if not self.cluster_registry:
            return override or self._get_placement_recommendation(
                request.hardware_profile or catalog_item.default_hardware_profile or "xeon-basic",
                catalog_item,
            )
        target = self.cluster_registry.select(
            required_capabilities=catalog_item.required_capabilities,
            required_models=required_models,
            override=override,
            require_public_access=request.exposure_policy == ExposurePolicy.PUBLIC_CODE,
            allow_disabled_override=allow_disabled_override,
        )
        return target.cluster_id

    def _run_preflight(self, catalog_item, cluster_ref: Optional[str]):
        """Validate models against the endpoints on the persisted target cluster."""
        model_endpoints = None
        if cluster_ref and self.cluster_registry:
            model_endpoints = self._target_config(cluster_ref).model_endpoints
        return self.preflight.check(
            catalog_item,
            model_endpoints=model_endpoints,
        )

    def _selected_model_endpoint(
        self, cluster_ref: Optional[str], selected_models: list[str]
    ) -> str:
        """Resolve the guide/runtime URL for the first model in this order."""
        if not selected_models:
            return ""
        if cluster_ref and self.cluster_registry:
            return self._target_config(cluster_ref).model_endpoints.get(
                selected_models[0], ""
            )
        return os.environ.get("LITELLM_API_BASE", "")

    def _get_gw_lock(self, gw_namespace: str) -> threading.Lock:
        if gw_namespace not in self._gw_locks:
            self._gw_locks[gw_namespace] = threading.Lock()
        return self._gw_locks[gw_namespace]

    def _save_request(self, request: LabRequest) -> None:
        self._requests[request.request_id] = request
        if self.db and hasattr(self.db, 'requests'):
            self.db.requests.save(request)

    def _save_session(self, session: LabSession) -> None:
        self._sessions[session.session_id] = session
        if self.db and hasattr(self.db, 'sessions'):
            self.db.sessions.save(session)

    def _save_plan(self, plan: ProvisioningPlan) -> None:
        self._plans[plan.plan_id] = plan
        if self.db and hasattr(self.db, 'plans'):
            self.db.plans.save(plan)

    def _save_workshop(self, workshop: Workshop) -> None:
        self._workshops[workshop.workshop_id] = workshop
        if self.db and hasattr(self.db, 'workshops'):
            self.db.workshops.save(workshop)

    def _resolve_hardware(self, request: LabRequest, catalog_item) -> tuple:
        if request.hardware_profile and request.quota_profile:
            return request.hardware_profile, request.quota_profile

        if self.brain:
            try:
                decision = self.brain.decide(request, catalog_item)
                self._last_decision = decision.model_dump()
                hw = request.hardware_profile or decision.recommended_hardware
                qp = request.quota_profile or decision.recommended_quota
                return hw, qp
            except Exception as e:
                logger.warning("OrchestrationBrain.decide() failed, falling back to classifier: %s", e)

        if self.workload_classifier:
            try:
                profile = self.workload_classifier.classify(catalog_item, request)
                matches = self.workload_classifier.match_hardware(profile)
                if matches:
                    hw = request.hardware_profile or matches[0].hardware_profile
                    qp = request.quota_profile or matches[0].right_sized_quota or catalog_item.default_quota_profile or "standard"
                    return hw, qp
            except Exception as e:
                logger.warning("WorkloadClassifier failed, falling back to defaults: %s", e)

        hw = request.hardware_profile or catalog_item.default_hardware_profile or "xeon-basic"
        qp = request.quota_profile or catalog_item.default_quota_profile or "standard"
        return hw, qp

    def _get_placement_recommendation(self, hardware_profile: str, catalog_item) -> Optional[str]:
        if not self.placement:
            return None
        try:
            rec = self.placement.recommend_cluster(
                hardware_profile,
                feedback_tracker=self.feedback_tracker,
                catalog_item_id=catalog_item.catalog_item_id if catalog_item else None,
            )
            if rec and not rec.fallback and rec.cluster_name:
                return rec.cluster_name
        except Exception as e:
            logger.warning("Placement recommendation failed: %s", e)
        return None

    def submit_request(self, request: LabRequest) -> LabRequest:
        catalog_item = self.catalog.get_item(request.catalog_item_id)
        if not catalog_item:
            request = request.model_copy(update={"status": LabRequestStatus.REJECTED})
            self._save_request(request)
            return request

        allowed_exposure_policies = (catalog_item.metadata or {}).get(
            "allowed_exposure_policies"
        )
        if (
            allowed_exposure_policies
            and request.exposure_policy.value not in allowed_exposure_policies
        ):
            request = request.model_copy(update={"status": LabRequestStatus.REJECTED})
            self._save_request(request)
            return request

        constraint_result: ConstraintResult = self.constraints.evaluate(request)
        if not constraint_result.allowed:
            request = request.model_copy(update={"status": LabRequestStatus.REJECTED})
            self._save_request(request)
            return request

        request = request.model_copy(update={"status": LabRequestStatus.ACCEPTED})
        self._save_request(request)
        return request

    # Session limits per user/tenant/workshop
    MAX_ACTIVE_PER_USER = int(os.environ.get("MAX_ACTIVE_SESSIONS_PER_USER", "2"))
    MAX_ACTIVE_PER_TENANT = int(os.environ.get("MAX_ACTIVE_SESSIONS_PER_TENANT", "5"))
    MAX_ACTIVE_PER_WORKSHOP = int(os.environ.get("MAX_ACTIVE_SESSIONS_PER_WORKSHOP", "50"))

    def _check_session_limits(self, request: LabRequest, workshop_id: str = None) -> None:
        active_statuses = {"requested", "provisioning", "validating", "ready", "active"}

        if workshop_id:
            workshop_active = sum(
                1 for s in self._sessions.values()
                if s.status.value in active_statuses
                and s.metadata.get("labels", {}).get("launchpad.redhat.com/workshop-id") == workshop_id
            )
            if workshop_active >= self.MAX_ACTIVE_PER_WORKSHOP:
                raise ValueError(
                    f"Workshop limit reached: {workshop_id} has "
                    f"{workshop_active} active session(s) (max {self.MAX_ACTIVE_PER_WORKSHOP})."
                )
            return

        user_active = sum(
            1 for s in self._sessions.values()
            if s.status.value in active_statuses and s.request_id in self._requests
            and self._requests[s.request_id].requester_id == request.requester_id
        )
        if user_active >= self.MAX_ACTIVE_PER_USER:
            raise ValueError(
                f"Session limit reached: {request.requester_id} already has "
                f"{user_active} active session(s) (max {self.MAX_ACTIVE_PER_USER}). "
                f"Reclaim an existing session before requesting a new one."
            )

        tenant_active = sum(
            1 for s in self._sessions.values()
            if s.status.value in active_statuses and s.tenant_id == request.tenant_id
        )
        if tenant_active >= self.MAX_ACTIVE_PER_TENANT:
            raise ValueError(
                f"Tenant limit reached: {request.tenant_id} has "
                f"{tenant_active} active session(s) (max {self.MAX_ACTIVE_PER_TENANT}). "
                f"Reclaim existing sessions before requesting new ones."
            )

    def provision(
        self,
        request_id: str,
        workshop_id: str = None,
        *,
        allow_disabled_target: bool = False,
    ) -> LabSession:
        request = self._requests.get(request_id)
        if not request:
            raise ValueError(f"Request {request_id} not found")
        if request.status != LabRequestStatus.ACCEPTED:
            raise ValueError(f"Request {request_id} is not accepted (status: {request.status.value})")

        self._check_session_limits(request, workshop_id=workshop_id)

        catalog_item = self.catalog.get_item(request.catalog_item_id)
        if not catalog_item:
            raise ValueError(f"Catalog item {request.catalog_item_id} not found")

        selected_models = request.requested_models or list(
            (catalog_item.metadata or {}).get("required_models", [])
        )
        if request.requested_models:
            catalog_item = catalog_item.model_copy(update={
                "metadata": {
                    **(catalog_item.metadata or {}),
                    "required_models": selected_models,
                }
            })

        hw, qp = self._resolve_hardware(request, catalog_item)
        preferred_cluster = self._select_target_cluster(
            request,
            catalog_item,
            allow_disabled_override=allow_disabled_target,
        )

        if self.preflight:
            preflight_result = self._run_preflight(catalog_item, preferred_cluster)
            if not preflight_result.passed:
                failed = [c for c in preflight_result.checks if c.status == "fail"]
                reasons = "; ".join(c.message for c in failed)
                raise ValueError(f"Preflight failed for {catalog_item.catalog_item_id}: {reasons}")

        target_pool = self._get_pool(preferred_cluster)
        if not target_pool.check_capacity(hw, qp):
            raise ValueError(f"No capacity available for hardware={hw} quota={qp}")

        reserve_kwargs = {"session_id": request.request_id, "hardware_profile": hw, "quota_profile": qp}
        if preferred_cluster:
            from app.adapters.rhdp.pool import RHDPPoolAdapter
            if isinstance(target_pool, RHDPPoolAdapter):
                reserve_kwargs["preferred_cluster"] = preferred_cluster
        reservation = target_pool.reserve(**reserve_kwargs)

        ttl_str = request.ttl or catalog_item.default_ttl or "4h"
        if self.maas_key_broker:
            metadata = catalog_item.metadata or {}
            try:
                issued_key = self.maas_key_broker.create_key(
                    alias=f"launchpad-{request.request_id}",
                    duration=ttl_str,
                    models=selected_models,
                    rpm_limit=int(metadata.get(
                        "maas_rpm_limit", os.environ.get("MAAS_RATE_LIMIT_RPM", "60")
                    )),
                    metadata={
                        "session_id": request.request_id,
                        "tenant_id": request.tenant_id,
                        "catalog_item_id": request.catalog_item_id,
                    },
                )
                maas_api_key = issued_key.key
            except Exception as exc:
                target_pool.release(request.request_id)
                raise ValueError(f"Failed to issue MaaS access key: {exc}") from exc
        else:
            maas_api_key = f"sk-launchpad-{_uuid.uuid4().hex[:24]}"

        provisioner = self._get_provisioner(catalog_item, preferred_cluster)
        plan = provisioner.create_plan(request, catalog_item)

        sandbox_data = {}
        if isinstance(reservation, dict):
            sandbox_data = reservation

        plan = plan.model_copy(update={
            "target_cluster": preferred_cluster,
            "required_resources": {
                **plan.required_resources,
                "requested_models": selected_models,
                "maas_endpoint": self._selected_model_endpoint(
                    preferred_cluster, selected_models
                ),
                "model_endpoints": (
                    dict(self._target_config(preferred_cluster).model_endpoints)
                    if preferred_cluster and self.cluster_registry
                    else {}
                ),
                "maas_api_key": maas_api_key,
                "sandbox_data": sandbox_data,
            }
        })
        # Persist the target before the first cluster mutation. This makes
        # retry, reconciliation, and cleanup deterministic after interruption.
        session = LabSession(
            request_id=request.request_id,
            tenant_id=request.tenant_id,
            catalog_item_id=request.catalog_item_id,
            namespace=plan.target_namespace,
            cluster_ref=preferred_cluster,
            maas_api_key=maas_api_key,
            resources={"cluster_id": preferred_cluster},
            metadata={
                "requested_models": selected_models,
                "labels": {
                    "launchpad.redhat.com/tenant": request.tenant_id,
                    "launchpad.redhat.com/catalog-item": request.catalog_item_id,
                    "launchpad.redhat.com/cluster-id": preferred_cluster or "local",
                }
            },
        )
        plan = plan.model_copy(update={
            "required_resources": {
                **plan.required_resources,
                "session_id": session.session_id,
            }
        })
        self._save_plan(plan)
        session = transition(session, SessionStatus.PROVISIONING, reason="target selected; provisioning started")
        self._save_session(session)
        self._save_request(request.model_copy(update={"status": LabRequestStatus.PROVISIONING}))

        try:
            result = provisioner.provision(plan)
        except Exception:
            logger.exception(
                "Provisioning failed for request %s on cluster %s",
                request.request_id,
                preferred_cluster,
            )
            raise

        if request.persistence == Persistence.PERSISTENT:
            expires_at = None
        else:
            expires_at = datetime.utcnow() + parse_ttl(ttl_str)

        dashboard_url = self.observability.create_dashboard(
            LabSession(
                request_id=request.request_id,
                tenant_id=request.tenant_id,
                catalog_item_id=request.catalog_item_id,
                namespace=result.namespace,
            )
        )

        cluster_ref = getattr(result, "cluster_ref", None) or sandbox_data.get("ingress_domain")

        session_labels = {
            "launchpad.redhat.com/tenant": request.tenant_id,
            "launchpad.redhat.com/catalog-item": request.catalog_item_id,
            "launchpad.redhat.com/purpose": sandbox_data.get("purpose", "self-service"),
        }

        session_resources = dict(result.resources)
        decision_data = getattr(self, "_last_decision", None)
        if decision_data:
            session_resources["decision"] = decision_data
            self._last_decision = None

        session = session.model_copy(update={
            "namespace": result.namespace,
            "cluster_ref": cluster_ref,
            "lab_url": result.lab_url,
            "dashboard_url": dashboard_url,
            "expires_at": expires_at,
            "resources": session_resources,
            "metadata": {
                **session.metadata,
                "labels": {**session.metadata.get("labels", {}), **session_labels},
            },
        })
        session = transition(session, SessionStatus.VALIDATING, reason="provisioning complete")

        self._save_session(session)
        return session

    def validate_session(self, session_id: str) -> LabSession:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if session.status == SessionStatus.VALIDATION_FAILED:
            session = transition(
                session, SessionStatus.VALIDATING, reason="validation retried"
            )

        results = self._get_validator(session.cluster_ref).validate(session)
        session = session.model_copy(update={"validation_results": results})

        has_failure = any(r.result.value == "fail" for r in results)
        if has_failure:
            session = transition(session, SessionStatus.VALIDATION_FAILED, reason="validation failed")
        else:
            session = transition(session, SessionStatus.READY, reason="all checks passed")

        self._save_session(session)
        notify_stargate(
            session_id=session.session_id,
            namespace=session.namespace,
            status=session.status.value,
            lab_code=session.catalog_item_id,
            tenant_id=session.tenant_id,
            error_summary="validation failed" if has_failure else "",
            resources=session.resources,
        )
        self._record_feedback(session, success=not has_failure,
                              failure_reason="validation failed" if has_failure else None)
        return session

    def _record_feedback(self, session: LabSession, success: bool,
                         failure_reason: Optional[str] = None) -> None:
        if not self.feedback_tracker:
            return
        try:
            from app.domain.feedback import ProvisioningOutcome
            request = self._requests.get(session.request_id)
            hw = "unknown"
            qp = "standard"
            if request:
                catalog_item = self.catalog.get_item(request.catalog_item_id)
                hw = request.hardware_profile or (catalog_item.default_hardware_profile if catalog_item else "unknown") or "unknown"
                qp = request.quota_profile or (catalog_item.default_quota_profile if catalog_item else "standard") or "standard"

            latency = 0
            if session.lifecycle_events and len(session.lifecycle_events) >= 2:
                start = session.lifecycle_events[0].timestamp
                end = session.lifecycle_events[-1].timestamp
                latency = int((end - start).total_seconds() * 1000)

            outcome = ProvisioningOutcome(
                session_id=session.session_id,
                request_id=session.request_id,
                catalog_item_id=session.catalog_item_id,
                cluster_name=session.cluster_ref,
                hardware_profile=hw,
                quota_profile=qp,
                success=success,
                failure_reason=failure_reason,
                provision_latency_ms=latency,
                validation_passed=success,
            )
            self.feedback_tracker.record_outcome(outcome)
        except Exception as e:
            logger.error("Failed to record provisioning feedback for session %s: %s", session.session_id, e)

    def activate_session(self, session_id: str) -> LabSession:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        session = transition(session, SessionStatus.ACTIVE, reason="lab activated")
        self._save_session(session)
        notify_stargate(
            session_id=session.session_id,
            namespace=session.namespace,
            status="active",
            lab_code=session.catalog_item_id,
            tenant_id=session.tenant_id,
            resources=session.resources,
        )
        return session

    def get_handoff(self, session_id: str) -> HandoffPackage:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        branding_request = self._requests.get(session.request_id)
        branding_meta = {}
        if branding_request and branding_request.branding_profile_id:
            profile = self.branding.load_profile(branding_request.branding_profile_id)
            if profile:
                branding_meta = {
                    "title": profile.title,
                    "primary_color": profile.primary_color,
                    "secondary_color": profile.secondary_color,
                    "theme": profile.theme.value,
                }

        catalog_item = self.catalog.get_item(session.catalog_item_id)
        lab_title = catalog_item.display_name if catalog_item else session.catalog_item_id

        return HandoffPackage(
            lab_title=lab_title,
            tenant=session.tenant_id,
            catalog_item=session.catalog_item_id,
            session_id=session.session_id,
            lab_url=session.lab_url,
            dashboard_url=session.dashboard_url,
            expires_at=session.expires_at,
            maas_api_key=session.maas_api_key,
            access_instructions="Open the lab URL and follow the on-screen instructions.",
            readme="1. Open the lab URL.\n2. Run the sample workload.\n3. View the dashboard.\n4. Export the report.",
            reset_instructions="Contact the lab administrator to reset your environment.",
            branding_metadata=branding_meta,
        )

    def get_showback(self, session_id: str) -> ShowbackRecord:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        return self.showback.create_record(session)

    def get_repeatability_report(self, session_id: str) -> RepeatabilityReport:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        plan = None
        for p in self._plans.values():
            if p.request_id == session.request_id:
                plan = p
                break
        plan_generated = plan is not None or any(
            event.to_status == SessionStatus.PROVISIONING
            for event in session.lifecycle_events
        )

        catalog_item = self.catalog.get_item(session.catalog_item_id)
        version = catalog_item.version if catalog_item else "unknown"

        validation_passed = (
            len(session.validation_results) > 0
            and all(r.result.value != "fail" for r in session.validation_results)
        )
        reached_handoff_state = session.status in (
            SessionStatus.READY,
            SessionStatus.ACTIVE,
        ) or any(
            event.to_status in (SessionStatus.READY, SessionStatus.ACTIVE)
            for event in session.lifecycle_events
        )

        return RepeatabilityReport(
            session_id=session.session_id,
            catalog_item_id=session.catalog_item_id,
            version=version,
            catalog_versioned=catalog_item is not None,
            # Plans are currently process-local, but the transition into
            # provisioning is persisted only after a plan is generated.
            provisioning_plan_generated=plan_generated,
            validation_passed=validation_passed,
            # Repeatability is historical evidence. A successful reclaim must
            # not erase proof that the session reached a handoff-ready state.
            handoff_generated=reached_handoff_state,
            showback_generated=True,
            cleanup_defined=True,
        )

    def get_security_plan(self, session_id: str) -> SecurityPlan:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        request = self._requests.get(session.request_id)
        catalog_item = self.catalog.get_item(session.catalog_item_id)
        quota = (
            (request.quota_profile if request else None)
            or (catalog_item.default_quota_profile if catalog_item else None)
            or "standard"
        )

        return SecurityPlan(
            namespace=session.namespace or f"lab-{session.tenant_id}",
            quota_profile=quota,
            rbac_profile="lab-user",
            network_policy_profile="restricted",
            secret_policy="no-external-secrets",
            egress_policy="deny-all-except-model-endpoint",
            notes=f"Security plan for session {session.session_id}",
        )

    def reset_session(self, session_id: str) -> LabSession:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        session = transition(session, SessionStatus.RESETTING, reason="reset requested")
        self._save_session(session)
        return session

    def reclaim_session(self, session_id: str) -> LabSession:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        if session.status not in (SessionStatus.RESETTING, SessionStatus.CLEANUP_FAILED):
            session = transition(session, SessionStatus.RESETTING, reason="cleanup started")
            self._save_session(session)
        self.pool.release(session.request_id)

        cleanup_errors = []
        if self.maas_key_broker and session.maas_api_key:
            try:
                self.maas_key_broker.revoke_key(session.maas_api_key)
            except Exception as e:
                cleanup_errors.append(f"MaaS key revocation failed: {e}")
        cleanup_adapter = self._get_cleanup(session.cluster_ref)
        if cleanup_adapter and session.resources.get("compose_file"):
            try:
                cleanup_adapter.cleanup(session.resources["compose_file"])
            except Exception as e:
                cleanup_errors.append(str(e))

        if cleanup_adapter and session.namespace:
            try:
                cleanup_adapter.cleanup(session.namespace)
            except Exception as e:
                cleanup_errors.append(str(e))

        if cleanup_adapter and session.resources.get("gateway_namespace"):
            gw_ns = session.resources["gateway_namespace"]
            with self._get_gw_lock(gw_ns):
                active_demos_for_gw = sum(
                    1 for s in self._sessions.values()
                    if s.session_id != session_id
                    and s.status.value in ("ready", "active", "validating", "provisioning")
                    and s.resources.get("gateway_namespace") == gw_ns
                )
                if active_demos_for_gw == 0:
                    try:
                        cleanup_adapter.cleanup(gw_ns)
                    except Exception as e:
                        cleanup_errors.append(str(e))

        session = self._scrub_credentials(session)

        if cleanup_errors:
            reason = f"cleanup failed — credentials scrubbed — errors: {'; '.join(cleanup_errors)}"
            if session.status != SessionStatus.CLEANUP_FAILED:
                session = transition(session, SessionStatus.CLEANUP_FAILED, reason=reason)
            self._save_session(session)
            notify_stargate(
                session_id=session.session_id,
                namespace=session.namespace,
                status="cleanup_failed",
                lab_code=session.catalog_item_id,
                tenant_id=session.tenant_id,
                error_summary="; ".join(cleanup_errors),
            )
        else:
            session = transition(session, SessionStatus.RECLAIMED, reason="resources reclaimed — credentials scrubbed")
            self._save_session(session)
            access = getattr(self, "public_access_service", None)
            if access:
                access.expire_order(session.request_id)
            notify_stargate(
                session_id=session.session_id,
                namespace=session.namespace,
                status="reclaimed",
                lab_code=session.catalog_item_id,
                tenant_id=session.tenant_id,
            )
        return session

    def force_reclaim_session(
        self, session_id: str, *, require_cleanup_success: bool = False
    ) -> LabSession:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        key_revocation_error = None
        if self.maas_key_broker and session.maas_api_key:
            try:
                self.maas_key_broker.revoke_key(session.maas_api_key)
            except Exception as exc:
                key_revocation_error = str(exc)
        self.pool.release(session.request_id)
        cleanup_adapter = self._get_cleanup(session.cluster_ref)
        if cleanup_adapter and session.resources.get("compose_file"):
            cleanup_adapter.cleanup(session.resources["compose_file"])
        if cleanup_adapter and session.resources.get("container_name"):
            cleanup_adapter.cleanup(session.resources["container_name"])
        if cleanup_adapter and session.namespace:
            try:
                cleanup_adapter.cleanup(session.namespace)
            except Exception as e:
                logger.error("Cleanup failed during force-reclaim of session %s namespace %s: %s", session_id, session.namespace, e)
                if require_cleanup_success:
                    reason = (
                        "force-reclaim cleanup failed — credentials scrubbed — "
                        f"error: {e}"
                    )
                    event = LifecycleEvent(
                        from_status=session.status,
                        to_status=SessionStatus.CLEANUP_FAILED,
                        reason=reason,
                    )
                    session = session.model_copy(update={
                        "status": SessionStatus.CLEANUP_FAILED,
                        "lifecycle_events": session.lifecycle_events + [event],
                    })
                    session = self._scrub_credentials(session)
                    self._save_session(session)
                    return session
        if key_revocation_error and require_cleanup_success:
            event = LifecycleEvent(
                from_status=session.status,
                to_status=SessionStatus.CLEANUP_FAILED,
                reason=f"force-reclaim MaaS key revocation failed: {key_revocation_error}",
            )
            session = session.model_copy(update={
                "status": SessionStatus.CLEANUP_FAILED,
                "lifecycle_events": session.lifecycle_events + [event],
            })
            session = self._scrub_credentials(session)
            self._save_session(session)
            return session
        event = LifecycleEvent(
            from_status=session.status,
            to_status=SessionStatus.RECLAIMED,
            reason="force reclaimed by admin — credentials scrubbed",
        )
        session = session.model_copy(
            update={
                "status": SessionStatus.RECLAIMED,
                "completed_at": datetime.utcnow(),
                "lifecycle_events": session.lifecycle_events + [event],
            }
        )
        session = self._scrub_credentials(session)
        self._save_session(session)
        return session

    def force_reclaim_catalog_sessions(self, catalog_item_id: str) -> dict:
        """Reclaim every non-reclaimed session for one catalog item.

        Workshop-backed sessions use the workshop lifecycle so queued workers
        are stopped and the aggregate record remains consistent. Standalone
        sessions use the existing force-reclaim path with cleanup verification.
        The operation is idempotent when a catalog has no remaining sessions.
        """
        targets = [
            session
            for session in self._sessions.values()
            if session.catalog_item_id == catalog_item_id
            and session.status != SessionStatus.RECLAIMED
        ]
        target_ids = {session.session_id for session in targets}
        workshop_ids: set[str] = set()
        for session in targets:
            request = self._requests.get(session.request_id)
            workshop_id = str(
                (request.metadata or {}).get("workshop_id", "") if request else ""
            ).strip()
            if workshop_id and workshop_id in self._workshops:
                workshop_ids.add(workshop_id)
        for workshop_id, workshop in self._workshops.items():
            if target_ids.intersection(workshop.session_ids):
                workshop_ids.add(workshop_id)

        failures: dict[str, str] = {}
        for workshop_id in sorted(workshop_ids):
            try:
                self.queue_workshop_reclaim(workshop_id)
                self.reclaim_workshop(workshop_id)
            except Exception as exc:  # noqa: BLE001 - report every failed group cleanup
                logger.exception(
                    "Catalog bulk force-reclaim failed for workshop %s", workshop_id
                )
                workshop = self._workshops.get(workshop_id)
                for session_id in workshop.session_ids if workshop else []:
                    if session_id in target_ids:
                        failures[session_id] = str(exc)

        remaining = [
            session_id
            for session_id in target_ids
            if self._sessions.get(session_id)
            and self._sessions[session_id].status != SessionStatus.RECLAIMED
        ]
        concurrency = max(
            1, min(10, int(os.environ.get("WORKSHOP_RECLAIM_CONCURRENCY", "10")))
        )
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(
                    self.force_reclaim_session,
                    session_id,
                    require_cleanup_success=True,
                ): session_id
                for session_id in remaining
            }
            for future in as_completed(futures):
                session_id = futures[future]
                try:
                    result = future.result()
                    if result.status != SessionStatus.RECLAIMED:
                        failures[session_id] = (
                            result.lifecycle_events[-1].reason
                            if result.lifecycle_events
                            else f"cleanup ended in {result.status.value}"
                        )
                    else:
                        failures.pop(session_id, None)
                except Exception as exc:  # noqa: BLE001 - aggregate partial failures
                    failures[session_id] = str(exc)

        results = []
        for session in targets:
            current = self._sessions.get(session.session_id, session)
            error = failures.get(session.session_id)
            results.append(
                {
                    "session_id": session.session_id,
                    "status": current.status.value,
                    "error": error,
                }
            )
        reclaimed_count = sum(
            item["status"] == SessionStatus.RECLAIMED.value for item in results
        )
        return {
            "catalog_item_id": catalog_item_id,
            "requested_count": len(targets),
            "reclaimed_count": reclaimed_count,
            "failed_count": len(results) - reclaimed_count,
            "results": results,
        }

    def _scrub_credentials(self, session: LabSession) -> LabSession:
        scrubbed_resources = {
            k: v for k, v in session.resources.items()
            if k not in ("sa_token", "sandbox_data")
        }
        session = session.model_copy(update={
            "maas_api_key": None,
            "resources": scrubbed_resources,
        })
        for plan in self._plans.values():
            if plan.request_id == session.request_id:
                scrubbed_plan_resources = {
                    k: v for k, v in plan.required_resources.items()
                    if k not in ("maas_api_key", "sandbox_data")
                }
                updated_plan = plan.model_copy(update={"required_resources": scrubbed_plan_resources})
                self._plans[plan.plan_id] = updated_plan
                self._save_plan(updated_plan)
        return session

    def get_session(self, session_id: str) -> Optional[LabSession]:
        return self._sessions.get(session_id)

    def get_session_public(self, session_id: str) -> Optional[LabSession]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        return session.model_copy(update={"maas_api_key": None})

    def reinitialize_session(self, session_id: str) -> LabSession:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        if session.status not in (SessionStatus.ACTIVE, SessionStatus.READY):
            raise ValueError(f"Session {session_id} is not active/ready (status: {session.status.value})")
        session = transition(session, SessionStatus.RESETTING, reason="reinitialize requested")
        session = transition(session, SessionStatus.VALIDATING, reason="reinitialize in progress")
        session = transition(session, SessionStatus.READY, reason="reinitialize complete")
        self._save_session(session)
        return session

    def get_request(self, request_id: str) -> Optional[LabRequest]:
        return self._requests.get(request_id)

    # ── Workshop provisioning ─────────────────────────────────────

    @staticmethod
    def _workshop_order_fingerprint(workshop: Workshop) -> str:
        order = {
            "tenant_id": workshop.tenant_id,
            "catalog_item_id": workshop.catalog_item_id,
            "num_users": workshop.num_users,
            "name": workshop.name,
            "owner_id": workshop.owner_id,
            "ttl": workshop.ttl,
            "ocp_version": workshop.ocp_version,
            "purpose": workshop.purpose,
            "exposure_policy": workshop.exposure_policy.value,
            "certification_override": workshop.certification_override,
        }
        return hashlib.sha256(json.dumps(order, sort_keys=True).encode()).hexdigest()

    def _with_default_workshop_name(self, workshop: Workshop) -> Workshop:
        """Use the catalog title when the caller does not supply an API name."""
        if workshop.name and workshop.name.strip():
            return workshop
        catalog_item = self.catalog.get_item(workshop.catalog_item_id)
        display_name = getattr(catalog_item, "display_name", None) if catalog_item else None
        return workshop.model_copy(
            update={"name": display_name or workshop.catalog_item_id}
        )

    @staticmethod
    def _workshop_seats(workshop: Workshop) -> list[WorkshopSeat]:
        if len(workshop.seats) == workshop.num_users:
            return workshop.seats
        return [
            WorkshopSeat(
                workshop_id=workshop.workshop_id,
                seat_number=index,
                participant_id=f"workshop-{workshop.workshop_id[:8]}-user-{index}",
            )
            for index in range(1, workshop.num_users + 1)
        ]

    def _validate_workshop_seat_limit(self, workshop: Workshop) -> int | None:
        """Enforce the smaller of the platform and catalog certification limits."""
        platform_limit = int(
            os.environ.get(
                "MAX_ACTIVE_SESSIONS_PER_WORKSHOP",
                str(self.MAX_ACTIVE_PER_WORKSHOP),
            )
        )
        if workshop.num_users > platform_limit:
            raise ValueError(
                f"Workshop seat count exceeds the supported limit of {platform_limit}"
            )

        catalog_item = self.catalog.get_item(workshop.catalog_item_id)
        allowed_exposure_policies = (
            (catalog_item.metadata or {}).get("allowed_exposure_policies")
            if catalog_item
            else None
        )
        if (
            allowed_exposure_policies
            and workshop.exposure_policy.value not in allowed_exposure_policies
        ):
            raise ValueError(
                f"{workshop.catalog_item_id} does not allow "
                f"{workshop.exposure_policy.value} exposure"
            )
        raw_catalog_limit = (
            (catalog_item.metadata or {}).get("max_workshop_seats")
            if catalog_item
            else None
        )
        if raw_catalog_limit is None:
            return None
        catalog_limit = int(raw_catalog_limit)
        if catalog_limit < 1:
            raise ValueError(
                f"{workshop.catalog_item_id} has an invalid workshop seat limit"
            )
        if workshop.num_users > catalog_limit:
            if not workshop.certification_override:
                raise ValueError(
                    f"{workshop.catalog_item_id} is certified for a maximum of "
                    f"{catalog_limit} workshop seat(s)"
                )
            if workshop.exposure_policy != ExposurePolicy.INTERNAL:
                raise ValueError(
                    "Workshop certification overrides are available for internal workshops only"
                )
            sequence = sorted({
                int(value)
                for value in (catalog_item.metadata or {}).get(
                    "promotion_sequence", []
                )
                if int(value) > catalog_limit
            })
            if not sequence:
                raise ValueError(
                    f"{workshop.catalog_item_id} does not declare a next certification target"
                )
            next_target = sequence[0]
            if workshop.num_users != next_target:
                raise ValueError(
                    "Workshop certification override permits only the next "
                    f"promotion target of {next_target} seat(s)"
                )
        return catalog_limit

    def preview_workshop_capacity(self, workshop: Workshop) -> dict:
        catalog_item = self.catalog.get_item(workshop.catalog_item_id)
        catalog_limit = None
        try:
            catalog_limit = self._validate_workshop_seat_limit(workshop)
        except ValueError as exc:
            metadata = catalog_item.metadata if catalog_item else {}
            return {
                "can_provision": False,
                "reason": str(exc),
                "selected_cluster": workshop.cluster_ref or workshop.target_cluster,
                "placement_reason": "catalog certification limit",
                "catalog_seat_limit": int(
                    metadata.get("max_workshop_seats", self.MAX_ACTIVE_PER_WORKSHOP)
                ),
                "seats_requested": workshop.num_users,
                "estimated_resources": {
                    "cpu_millicores": 0,
                    "memory_mib": 0,
                    "pods": 0,
                },
            }
        selected_cluster = workshop.cluster_ref or workshop.target_cluster
        if self.cluster_registry and catalog_item:
            try:
                selected_cluster = self.cluster_registry.select(
                    required_capabilities=catalog_item.required_capabilities,
                    required_models=(catalog_item.metadata or {}).get("required_models", []),
                    override=workshop.target_cluster,
                    require_public_access=workshop.exposure_policy == ExposurePolicy.PUBLIC_CODE,
                    allow_disabled_override=workshop.certification_override,
                ).cluster_id
            except ValueError as exc:
                return {
                    "can_provision": False,
                    "reason": str(exc),
                    "selected_cluster": None,
                    "placement_reason": str(exc),
                    "seats_requested": workshop.num_users,
                    "estimated_resources": {"cpu_millicores": 0, "memory_mib": 0, "pods": 0},
                }
            workshop = workshop.model_copy(update={"cluster_ref": selected_cluster})
        can_provision, reason = self.check_workshop_capacity(workshop)
        metadata = catalog_item.metadata if catalog_item else {}
        estimate = self._workshop_resource_estimate(
            metadata, workshop.num_users
        )
        return {
            "can_provision": can_provision,
            "reason": reason,
            "selected_cluster": selected_cluster,
            "placement_reason": (
                f"Entire workshop assigned to {selected_cluster}; seats will not be split"
                if selected_cluster else "single-cluster placement"
            ),
            "seats_requested": workshop.num_users,
            "catalog_seat_limit": catalog_limit,
            "certification_override": workshop.certification_override,
            "certification_target_seats": (
                workshop.num_users if workshop.certification_override else None
            ),
            "estimated_resources": {
                "cpu_millicores": estimate["cpu_millicores"],
                "memory_mib": estimate["memory_mib"],
                "pods": estimate["pods"],
            },
            "resource_breakdown": {
                "shared": estimate["shared"],
                "per_seat": estimate["per_seat"],
                "transient": estimate["transient"],
            },
        }

    def _wait_for_workshop_stability(
        self, seats: list[WorkshopSeat]
    ) -> dict[int, str]:
        """Require every Showroom endpoint to be healthy at the same time.

        Per-seat provisioning checks prove that each route worked once. This
        final sweep prevents an early seat that later regresses from being
        hidden by subsequent provisioning waves.
        """
        if os.environ.get("LAUNCHPAD_MODE", "mock") != "openshift":
            return {}

        import requests

        candidates = {
            seat.seat_number: seat.showroom_url or seat.lab_url
            for seat in seats
            if seat.status == WorkshopSeatStatus.READY
            and (seat.showroom_url or seat.lab_url)
        }
        if not candidates:
            return {}

        timeout = max(
            1, int(os.environ.get("WORKSHOP_STABILITY_TIMEOUT", "120"))
        )
        interval = max(
            0.1, float(os.environ.get("WORKSHOP_STABILITY_INTERVAL", "5"))
        )
        required_passes = max(
            1, int(os.environ.get("WORKSHOP_STABILITY_PASSES", "3"))
        )
        tls_verify: bool | str = (
            os.environ.get("REQUESTS_CA_BUNDLE")
            or os.environ.get("SSL_CERT_FILE")
            or True
        )
        deadline = time.monotonic() + timeout
        consecutive_passes = 0
        failures: dict[int, str] = {}

        while time.monotonic() < deadline:
            failures = {}

            def check_endpoint(item: tuple[int, str]) -> tuple[int, str | None]:
                seat_number, url = item
                try:
                    response = requests.get(url, timeout=10, verify=tls_verify)
                    if response.status_code == 200:
                        return seat_number, None
                    return seat_number, f"showroom endpoint returned HTTP {response.status_code}"
                except requests.RequestException as exc:
                    return seat_number, f"showroom endpoint check failed: {exc}"

            with ThreadPoolExecutor(max_workers=min(10, len(candidates))) as executor:
                for seat_number, error in executor.map(
                    check_endpoint, candidates.items()
                ):
                    if error:
                        failures[seat_number] = error

            if not failures:
                consecutive_passes += 1
                if consecutive_passes >= required_passes:
                    return {}
            else:
                consecutive_passes = 0
            time.sleep(interval)

        return failures or {
            seat_number: "showroom endpoint did not remain stable"
            for seat_number in candidates
        }

    def create_workshop_order(
        self, workshop: Workshop, idempotency_key: str = None
    ) -> Workshop:
        workshop = self._with_default_workshop_name(workshop)
        self._validate_workshop_seat_limit(workshop)
        fingerprint = self._workshop_order_fingerprint(workshop)
        if idempotency_key:
            lookup_key = (workshop.tenant_id, idempotency_key)
            existing = self._workshop_idempotency.get(lookup_key)
            if existing:
                existing_fingerprint, workshop_id = existing
                if existing_fingerprint != fingerprint:
                    raise ValueError(
                        "Idempotency key was already used for a different workshop order"
                    )
                return self._workshops[workshop_id]
            self._workshop_idempotency[lookup_key] = (
                fingerprint,
                workshop.workshop_id,
            )

        preview = self.preview_workshop_capacity(workshop)
        status = (
            WorkshopStatus.AWAITING_CONFIRMATION
            if preview["can_provision"]
            else WorkshopStatus.FAILED
        )
        order = workshop.model_copy(update={
            "status": status,
            "seats": self._workshop_seats(workshop),
            "idempotency_key": idempotency_key,
            "order_fingerprint": fingerprint if idempotency_key else None,
            "cluster_ref": preview.get("selected_cluster"),
            "metadata": {**workshop.metadata, "capacity_preview": preview},
        })
        self._save_workshop(order)
        return order

    def confirm_workshop(self, workshop_id: str) -> Workshop:
        workshop = self._workshops.get(workshop_id)
        if not workshop:
            raise ValueError(f"Workshop {workshop_id} not found")
        if workshop.status in {
            WorkshopStatus.PROVISIONING,
            WorkshopStatus.PARTIALLY_READY,
            WorkshopStatus.READY,
            WorkshopStatus.ACTIVE,
        }:
            return workshop
        if workshop.status != WorkshopStatus.AWAITING_CONFIRMATION:
            raise ValueError(
                f"Workshop {workshop_id} cannot be confirmed from status {workshop.status.value}"
            )
        return self.provision_workshop(workshop)

    def queue_workshop(self, workshop_id: str) -> Workshop:
        workshop = self._workshops.get(workshop_id)
        if not workshop:
            raise ValueError(f"Workshop {workshop_id} not found")
        if workshop.status in {
            WorkshopStatus.QUEUED,
            WorkshopStatus.PROVISIONING,
            WorkshopStatus.PARTIALLY_READY,
            WorkshopStatus.READY,
            WorkshopStatus.ACTIVE,
        }:
            return workshop
        if workshop.status != WorkshopStatus.AWAITING_CONFIRMATION:
            raise ValueError(
                f"Workshop {workshop_id} cannot be queued from status {workshop.status.value}"
            )
        queued = workshop.model_copy(update={"status": WorkshopStatus.QUEUED})
        self._save_workshop(queued)
        return queued

    def run_queued_workshop(self, workshop_id: str) -> Workshop:
        workshop = self._workshops.get(workshop_id)
        if not workshop:
            raise ValueError(f"Workshop {workshop_id} not found")
        if workshop.status in {
            WorkshopStatus.PARTIALLY_READY,
            WorkshopStatus.READY,
            WorkshopStatus.ACTIVE,
        }:
            return workshop
        if workshop.status not in {
            WorkshopStatus.QUEUED,
            WorkshopStatus.PROVISIONING,
        }:
            raise ValueError(
                f"Workshop {workshop_id} cannot run from status {workshop.status.value}"
            )
        return self.provision_workshop(workshop)

    def queue_failed_workshop_seats(self, workshop_id: str) -> Workshop:
        workshop = self._workshops.get(workshop_id)
        if not workshop:
            raise ValueError(f"Workshop {workshop_id} not found")
        incomplete = [
            seat for seat in workshop.seats
            if seat.status != WorkshopSeatStatus.READY
        ]
        if not incomplete:
            raise ValueError(f"Workshop {workshop_id} has no incomplete seats to retry")
        seats = [
            seat.model_copy(update={
                "status": WorkshopSeatStatus.PENDING,
                "error": None,
                "updated_at": datetime.utcnow(),
            }) if seat.status != WorkshopSeatStatus.READY else seat
            for seat in workshop.seats
        ]
        stale_failure_keys = {"error", "preflight_failure", "readiness_failures"}
        metadata = {
            key: value
            for key, value in workshop.metadata.items()
            if key not in stale_failure_keys
        }
        queued = workshop.model_copy(update={
            "status": WorkshopStatus.QUEUED,
            "seats": seats,
            "metadata": metadata,
        })
        self._save_workshop(queued)
        return queued

    def _link_persisted_workshop_sessions(self, workshop: Workshop) -> Workshop:
        """Recover seat links when provisioning stopped after session persistence."""
        seats = list(workshop.seats)
        seats_by_id = {seat.seat_id: index for index, seat in enumerate(seats)}
        session_ids = [
            seat.session_id
            for seat in seats
            if seat.session_id
        ]
        candidates: dict[int, list[tuple[int, LabSession, LabRequest]]] = {}
        for position, session in enumerate(self._sessions.values()):
            request = self._requests.get(session.request_id)
            request_metadata = request.metadata if request else {}
            if request_metadata.get("workshop_id") != workshop.workshop_id:
                continue
            seat_index = seats_by_id.get(request_metadata.get("seat_id"))
            if seat_index is None or seats[seat_index].session_id:
                continue
            candidates.setdefault(seat_index, []).append((position, session, request))

        def recovery_rank(candidate: tuple[int, LabSession, LabRequest]):
            position, session, _request = candidate
            latest_event = max(
                (event.timestamp for event in session.lifecycle_events),
                default=datetime.min,
            )
            return (
                session.status != SessionStatus.RECLAIMED,
                latest_event,
                position,
            )

        for seat_index, seat_candidates in candidates.items():
            _position, session, request = max(seat_candidates, key=recovery_rank)
            session_ids.append(session.session_id)
            seats[seat_index] = seats[seat_index].model_copy(
                update={
                    "status": WorkshopSeatStatus.RECLAIMING,
                    "session_id": session.session_id,
                    "request_id": request.request_id,
                    "updated_at": datetime.utcnow(),
                }
            )
        return workshop.model_copy(update={"session_ids": session_ids, "seats": seats})

    def _authoritative_workshop_stop_state(
        self, workshop_id: str
    ) -> Optional[Workshop]:
        """Return a persisted state that forbids publishing more seat results.

        A backend replacement can briefly leave an old process finishing a
        Kubernetes mutation while the replacement process reclaims the same
        workshop.  The database, rather than either process-local cache, is
        authoritative for stop states.  Late workers must observe that state
        and reclaim any unlinked session they just created.
        """
        stop_states = {
            WorkshopStatus.RECLAIMING,
            WorkshopStatus.COMPLETED,
            WorkshopStatus.COMPLETED_WITH_ERRORS,
        }
        current = self._workshops.get(workshop_id)
        store = getattr(self.db, "workshops", None) if self.db else None
        get_persisted = getattr(store, "get", None)
        if callable(get_persisted):
            persisted = get_persisted(workshop_id)
            if persisted and persisted.status in stop_states:
                self._workshops[workshop_id] = persisted
                return persisted
        return current if current and current.status in stop_states else None

    def _discard_late_workshop_session(
        self, workshop: Workshop, session_id: Optional[str]
    ) -> Workshop:
        """Reclaim a seat result produced after workshop shutdown began."""
        if not session_id or session_id in workshop.session_ids:
            return workshop
        error = self._reclaim_workshop_session(session_id)
        if not error:
            return workshop
        failed = list(workshop.metadata.get("failed_late_seat_reclaims", []))
        failed.append({"session_id": session_id, "error": error})
        updated = workshop.model_copy(
            update={
                "status": WorkshopStatus.COMPLETED_WITH_ERRORS,
                "metadata": {
                    **workshop.metadata,
                    "failed_late_seat_reclaims": failed,
                },
            }
        )
        self._save_workshop(updated)
        return updated

    def _cleanup_interrupted_workshop_sessions(self, workshop: Workshop) -> Workshop:
        """Remove every partial seat session before retrying an interrupted order.

        A worker can stop after persisting the session and mutating the target
        cluster but before copying the session ID onto its workshop seat. A new
        session for that same seat would then conflict with ownership labels on
        the surviving resources. Reclaim all persisted, non-ready seat sessions
        first and fail closed if any cleanup cannot be proved successful.
        """
        seats = list(workshop.seats)
        seats_by_id = {seat.seat_id: index for index, seat in enumerate(seats)}
        session_ids = list(workshop.session_ids)
        partial_sessions: list[tuple[int, LabSession]] = []
        for session in self._sessions.values():
            request = self._requests.get(session.request_id)
            metadata = request.metadata if request else {}
            if metadata.get("workshop_id") != workshop.workshop_id:
                continue
            seat_index = seats_by_id.get(metadata.get("seat_id"))
            if seat_index is None or seats[seat_index].status == WorkshopSeatStatus.READY:
                continue
            partial_sessions.append((seat_index, session))

        for seat_index, session in partial_sessions:
            if session.status != SessionStatus.RECLAIMED:
                cleanup_error = self._reclaim_workshop_session(session.session_id)
                if cleanup_error:
                    raise ValueError(
                        f"Interrupted seat cleanup failed for {session.session_id}: "
                        f"{cleanup_error}"
                    )
            cleanup_adapter = self._get_cleanup(session.cluster_ref)
            wait_until_absent = getattr(cleanup_adapter, "wait_until_absent", None)
            if session.namespace and callable(wait_until_absent):
                delete_timeout = max(
                    1,
                    int(
                        os.environ.get(
                            "WORKSHOP_RETRY_NAMESPACE_DELETE_TIMEOUT", "180"
                        )
                    ),
                )
                wait_until_absent(session.namespace, timeout=delete_timeout)
            if session.session_id in session_ids:
                session_ids.remove(session.session_id)
            seats[seat_index] = seats[seat_index].model_copy(
                update={
                    "status": WorkshopSeatStatus.PENDING,
                    "session_id": None,
                    "request_id": None,
                    "lab_url": None,
                    "showroom_url": None,
                    "error": None,
                    "updated_at": datetime.utcnow(),
                }
            )

        recovered = workshop.model_copy(update={"session_ids": session_ids, "seats": seats})
        self._save_workshop(recovered)
        return recovered

    def recover_interrupted_workshops(self) -> list[str]:
        """Resume workshop provision or reclaim jobs interrupted with the process.

        Workshop and seat state is persisted, but the worker thread is not. On
        process startup, reset only incomplete seats and reuse every completed
        seat/session. Resource reconciliation runs while the service loads and
        removes any unlinked partial session before this method creates a
        replacement, preventing duplicate live namespaces for one seat. A
        reclaim can be requested while a seat is still provisioning, before
        the worker has copied its persisted session ID onto the seat. Recover
        that link from the persisted request metadata before resuming cleanup.
        """
        reclaiming = [
            workshop.workshop_id
            for workshop in list(self._workshops.values())
            if workshop.status == WorkshopStatus.RECLAIMING
        ]
        interrupted = [
            workshop.workshop_id
            for workshop in list(self._workshops.values())
            if workshop.status in {
                WorkshopStatus.QUEUED,
                WorkshopStatus.PROVISIONING,
            }
        ]
        recovered: list[str] = []
        for workshop_id in reclaiming:
            try:
                workshop = self._link_persisted_workshop_sessions(
                    self._workshops[workshop_id]
                )
                self._save_workshop(workshop)
                self.reclaim_workshop(workshop_id)
                recovered.append(workshop_id)
            except Exception:
                logger.exception(
                    "Automatic reclaim recovery failed for workshop %s",
                    workshop_id,
                )
        for workshop_id in interrupted:
            try:
                workshop = self._workshops[workshop_id]
                if workshop.status == WorkshopStatus.PROVISIONING:
                    workshop = self._cleanup_interrupted_workshop_sessions(workshop)
                    self.queue_failed_workshop_seats(workshop_id)
                self.run_queued_workshop(workshop_id)
                recovered.append(workshop_id)
            except Exception:
                logger.exception(
                    "Automatic recovery failed for workshop %s", workshop_id
                )
        return recovered

    def provision_workshop(
        self, workshop: Workshop, idempotency_key: str = None
    ) -> Workshop:
        workshop = self._with_default_workshop_name(workshop)
        provision_event = self._workshop_provision_events.setdefault(
            workshop.workshop_id, threading.Event()
        )
        provision_event.clear()
        try:
            self._validate_workshop_seat_limit(workshop)
        except ValueError:
            provision_event.set()
            raise
        if idempotency_key:
            lookup_key = (workshop.tenant_id, idempotency_key)
            fingerprint = self._workshop_order_fingerprint(workshop)
            existing = self._workshop_idempotency.get(lookup_key)
            if existing:
                existing_fingerprint, workshop_id = existing
                if existing_fingerprint != fingerprint:
                    raise ValueError(
                        "Idempotency key was already used for a different workshop order"
                    )
                return self._workshops[workshop_id]
            self._workshop_idempotency[lookup_key] = (fingerprint, workshop.workshop_id)
            workshop = workshop.model_copy(update={
                "idempotency_key": idempotency_key,
                "order_fingerprint": fingerprint,
            })

        seats = self._workshop_seats(workshop)
        workshop = workshop.model_copy(update={
            "status": WorkshopStatus.PROVISIONING,
            "started_at": datetime.utcnow(),
            "seats": seats,
        })
        self._save_workshop(workshop)

        catalog_item = self.catalog.get_item(workshop.catalog_item_id)
        if not catalog_item:
            workshop = workshop.model_copy(update={"status": WorkshopStatus.FAILED, "metadata": {**workshop.metadata, "error": "catalog item not found"}})
            self._save_workshop(workshop)
            provision_event.set()
            return workshop

        # The direct create-and-provision API does not pass through
        # create_workshop_order(), so it must persist placement here before
        # any seat request is created.  Otherwise each seat independently
        # falls back to automatic placement and the workshop loses its
        # single-cluster affinity (and its cleanup target).
        if self.cluster_registry:
            try:
                selected_cluster = self.cluster_registry.select(
                    required_capabilities=catalog_item.required_capabilities,
                    required_models=(catalog_item.metadata or {}).get(
                        "required_models", []
                    ),
                    override=workshop.cluster_ref or workshop.target_cluster,
                    require_public_access=workshop.exposure_policy == ExposurePolicy.PUBLIC_CODE,
                    allow_disabled_override=workshop.certification_override,
                ).cluster_id
            except ValueError as exc:
                workshop = workshop.model_copy(update={
                    "status": WorkshopStatus.FAILED,
                    "metadata": {**workshop.metadata, "error": str(exc)},
                })
                self._save_workshop(workshop)
                provision_event.set()
                return workshop
            workshop = workshop.model_copy(update={"cluster_ref": selected_cluster})
            self._save_workshop(workshop)

        if self.preflight:
            preflight_result = self._run_preflight(
                catalog_item, workshop.cluster_ref
            )
            if not preflight_result.passed:
                failed = [c for c in preflight_result.checks if c.status == "fail"]
                reasons = "; ".join(c.message for c in failed)
                workshop = workshop.model_copy(update={
                    "status": WorkshopStatus.PREFLIGHT_FAILED,
                    "metadata": {**workshop.metadata, "preflight_failure": reasons},
                })
                self._save_workshop(workshop)
                provision_event.set()
                return workshop

        # Capacity is revalidated immediately before mutations. On retry,
        # existing seat sessions already consume cluster capacity, so only
        # seats that still require a new session belong in this calculation.
        seats_requiring_capacity = sum(
            1
            for seat in workshop.seats
            if seat.status != WorkshopSeatStatus.READY
            and not (seat.session_id and self._sessions.get(seat.session_id))
        )
        if seats_requiring_capacity:
            capacity_request = workshop.model_copy(
                update={"num_users": seats_requiring_capacity}
            )
            can_provision, cap_reason = self.check_workshop_capacity(capacity_request)
            if not can_provision:
                workshop = workshop.model_copy(update={
                    "status": WorkshopStatus.FAILED,
                    "metadata": {**workshop.metadata, "error": f"Insufficient capacity: {cap_reason}"},
                })
                self._save_workshop(workshop)
                provision_event.set()
                return workshop

        workshop_limit = int(os.environ.get("MAX_ACTIVE_SESSIONS_PER_WORKSHOP", str(self.MAX_ACTIVE_PER_WORKSHOP)))
        seats_to_provision = min(workshop.num_users, workshop_limit)

        session_ids = []
        pending_indexes = []
        for i in range(seats_to_provision):
            seat = workshop.seats[i]
            if seat.status == WorkshopSeatStatus.READY and seat.session_id:
                session_ids.append(seat.session_id)
                continue
            existing_session = (
                self._sessions.get(seat.session_id) if seat.session_id else None
            )
            if existing_session:
                try:
                    if existing_session.status == SessionStatus.VALIDATION_FAILED:
                        existing_session = self.validate_session(
                            existing_session.session_id
                        )
                except Exception as exc:
                    logger.warning(
                        "Workshop %s seat %d revalidation failed: %s",
                        workshop.workshop_id,
                        i + 1,
                        exc,
                    )
                    workshop.seats[i] = seat.model_copy(update={
                        "status": WorkshopSeatStatus.FAILED,
                        "error": f"seat revalidation failed: {exc}",
                        "updated_at": datetime.utcnow(),
                    })
                    continue

                if existing_session.status in {
                    SessionStatus.READY,
                    SessionStatus.ACTIVE,
                }:
                    workshop.seats[i] = seat.model_copy(update={
                        "status": WorkshopSeatStatus.READY,
                        "error": None,
                        "updated_at": datetime.utcnow(),
                    })
                    session_ids.append(existing_session.session_id)
                else:
                    workshop.seats[i] = seat.model_copy(update={
                        "status": WorkshopSeatStatus.FAILED,
                        "error": (
                            "existing seat session is not ready: "
                            f"{existing_session.status.value}"
                        ),
                        "updated_at": datetime.utcnow(),
                    })
                continue
            workshop.seats[i] = seat.model_copy(update={
                "status": WorkshopSeatStatus.PROVISIONING,
                "updated_at": datetime.utcnow(),
            })
            pending_indexes.append(i)
        self._save_workshop(workshop)

        catalog_item = self.catalog.get_item(workshop.catalog_item_id)
        catalog_metadata = catalog_item.metadata if catalog_item else {}
        concurrency = max(1, int(catalog_metadata.get(
            "workshop_provision_concurrency",
            os.environ.get("WORKSHOP_PROVISION_CONCURRENCY", "5"),
        )))
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(
                    self._provision_workshop_seat_unless_reclaiming,
                    workshop,
                    i,
                ): i
                for i in pending_indexes
            }
            for future in as_completed(futures):
                i = futures[future]
                try:
                    updated_seat, session_id = future.result()
                except Exception as exc:
                    logger.exception(
                        "Workshop %s seat %d failed unexpectedly",
                        workshop.workshop_id,
                        i + 1,
                    )
                    updated_seat = workshop.seats[i].model_copy(update={
                        "status": WorkshopSeatStatus.FAILED,
                        "error": str(exc),
                        "updated_at": datetime.utcnow(),
                    })
                    session_id = None

                # A different backend process may have reclaimed this order
                # while this worker was blocked in a cluster API call.  Never
                # overwrite that durable stop state or strand the late seat.
                stopped = self._authoritative_workshop_stop_state(
                    workshop.workshop_id
                )
                if stopped:
                    workshop = self._discard_late_workshop_session(
                        stopped, session_id
                    )
                    continue

                workshop.seats[i] = updated_seat
                if session_id:
                    session_ids.append(session_id)
                current = self._workshops.get(workshop.workshop_id)
                if current and current.status == WorkshopStatus.RECLAIMING:
                    workshop = current.model_copy(update={
                        "seats": workshop.seats,
                        "session_ids": list(dict.fromkeys(session_ids)),
                    })
                else:
                    workshop = workshop.model_copy(update={
                        "session_ids": list(dict.fromkeys(session_ids)),
                    })
                self._save_workshop(workshop)

        current = self._authoritative_workshop_stop_state(workshop.workshop_id)
        if current and current.status == WorkshopStatus.RECLAIMING:
            workshop = current.model_copy(update={
                "seats": workshop.seats,
                "session_ids": list(dict.fromkeys(session_ids)),
                "metadata": {
                    **current.metadata,
                    "seats_requested": workshop.num_users,
                    "seats_provisioned": len(session_ids),
                },
            })
            self._save_workshop(workshop)
            provision_event.set()
            return workshop
        if current:
            provision_event.set()
            return current

        readiness_failures = self._wait_for_workshop_stability(workshop.seats)
        if readiness_failures:
            for index, seat in enumerate(workshop.seats):
                error = readiness_failures.get(seat.seat_number)
                if not error:
                    continue
                workshop.seats[index] = seat.model_copy(update={
                    "status": WorkshopSeatStatus.FAILED,
                    "error": error,
                    "updated_at": datetime.utcnow(),
                })
                if seat.session_id in session_ids:
                    session_ids.remove(seat.session_id)

        session_ids.sort(key=lambda session_id: next(
            (
                seat.seat_number
                for seat in workshop.seats
                if seat.session_id == session_id
            ),
            workshop.num_users + 1,
        ))

        if len(session_ids) == workshop.num_users:
            status = WorkshopStatus.READY
        elif session_ids:
            status = WorkshopStatus.PARTIALLY_READY
        else:
            status = WorkshopStatus.FAILED
        workshop = workshop.model_copy(update={
            "status": status,
            "session_ids": session_ids,
            "metadata": {
                **workshop.metadata,
                "seats_requested": workshop.num_users,
                "seats_provisioned": len(session_ids),
                "readiness_failures": {
                    str(seat_number): error
                    for seat_number, error in readiness_failures.items()
                },
            },
        })
        self._save_workshop(workshop)
        provision_event.set()
        return workshop

    def _provision_workshop_seat_unless_reclaiming(
        self, workshop: Workshop, index: int
    ) -> tuple[WorkshopSeat, Optional[str]]:
        """Do not start queued seat work after group reclaim is requested."""
        current = self._workshops.get(workshop.workshop_id)
        if current and current.status == WorkshopStatus.RECLAIMING:
            seat = current.seats[index]
            return seat.model_copy(
                update={
                    "status": WorkshopSeatStatus.PENDING,
                    "error": None,
                    "updated_at": datetime.utcnow(),
                }
            ), None
        return self._provision_workshop_seat(workshop, index)

    def _provision_workshop_seat(
        self, workshop: Workshop, index: int
    ) -> tuple[WorkshopSeat, Optional[str]]:
        seat = workshop.seats[index]
        request = LabRequest(
            tenant_id=workshop.tenant_id,
            requester_id=seat.participant_id,
            catalog_item_id=workshop.catalog_item_id,
            requested_mode=CatalogCategory.QUICK_START,
            ttl=workshop.ttl,
            metadata={
                "workshop_id": workshop.workshop_id,
                "seat_id": seat.seat_id,
                "seat_number": seat.seat_number,
                "participant_id": seat.participant_id,
                "purpose": workshop.purpose,
                "target_cluster": workshop.cluster_ref,
            },
        )
        accepted = self.submit_request(request)
        if accepted.status != LabRequestStatus.ACCEPTED:
            return seat.model_copy(update={
                "status": WorkshopSeatStatus.FAILED,
                "error": "seat request was rejected",
                "updated_at": datetime.utcnow(),
            }), None
        try:
            session = self.provision(
                accepted.request_id,
                workshop_id=workshop.workshop_id,
                allow_disabled_target=workshop.certification_override,
            )
            session = self.validate_session(session.session_id)
            if session.status != SessionStatus.READY:
                return seat.model_copy(update={
                    "status": WorkshopSeatStatus.FAILED,
                    "session_id": session.session_id,
                    "request_id": accepted.request_id,
                    "lab_url": session.lab_url,
                    "showroom_url": session.metadata.get("showroom_url") or session.lab_url,
                    "error": "seat validation failed",
                    "updated_at": datetime.utcnow(),
                }), None
            # A workshop is one order with one lifecycle boundary.  Computing
            # expiry independently in provision() made early seats disappear
            # while later seats from the same order still appeared ready.
            # Anchor every ephemeral seat to the persisted workshop start so
            # TTL enforcement can reclaim the order atomically.
            order_expires_at = (
                workshop.started_at + parse_ttl(workshop.ttl)
                if (
                    session.expires_at is not None
                    and workshop.started_at is not None
                )
                else session.expires_at
            )
            session = session.model_copy(update={
                "expires_at": order_expires_at,
                "metadata": {
                    **session.metadata,
                    "purpose": workshop.purpose,
                    "labels": {
                        **session.metadata.get("labels", {}),
                        "launchpad.redhat.com/workshop-id": workshop.workshop_id,
                        "launchpad.redhat.com/purpose": workshop.purpose,
                    },
                },
            })
            self._save_session(session)
            return seat.model_copy(update={
                "status": WorkshopSeatStatus.READY,
                "session_id": session.session_id,
                "request_id": accepted.request_id,
                "lab_url": session.lab_url,
                "showroom_url": session.metadata.get("showroom_url") or session.lab_url,
                "updated_at": datetime.utcnow(),
            }), session.session_id
        except ValueError as exc:
            logger.warning(
                "Workshop %s seat %d failed: %s",
                workshop.workshop_id,
                index + 1,
                exc,
            )
            return seat.model_copy(update={
                "status": WorkshopSeatStatus.FAILED,
                "error": str(exc),
                "updated_at": datetime.utcnow(),
            }), None

    def get_workshop_users(self, workshop_id: str) -> list:
        workshop = self._workshops.get(workshop_id)
        if not workshop:
            raise ValueError(f"Workshop {workshop_id} not found")
        users = []
        for session_id in workshop.session_ids:
            session = self._sessions.get(session_id)
            if not session:
                continue
            request = self._requests.get(session.request_id)
            users.append({
                "session_id": session.session_id,
                "user_id": request.requester_id if request else "unknown",
                "lab_url": session.lab_url,
                "dashboard_url": session.dashboard_url,
                "status": session.status.value,
                "expires_at": session.expires_at.isoformat() if session.expires_at else None,
            })
        return users

    @staticmethod
    def _workshop_schedulable_nodes(nodes: list) -> list:
        """Return nodes that ordinary, untolerated workshop pods can use.

        Control-plane allocatable resources are not workshop capacity, and a
        NotReady or cordoned worker must stop contributing immediately.
        """
        eligible = []
        for node in nodes:
            spec = getattr(node, "spec", None)
            if bool(getattr(spec, "unschedulable", False)):
                continue
            taints = list(getattr(spec, "taints", None) or [])
            if any(
                str(getattr(taint, "effect", "")) in {"NoSchedule", "NoExecute"}
                for taint in taints
            ):
                continue
            conditions = list(getattr(getattr(node, "status", None), "conditions", None) or [])
            ready = next(
                (
                    str(getattr(condition, "status", "")) == "True"
                    for condition in conditions
                    if str(getattr(condition, "type", "")) == "Ready"
                ),
                True,
            )
            if not ready:
                continue
            eligible.append(node)
        return eligible

    @classmethod
    def _workshop_catalog_nodes(cls, nodes: list, metadata: dict) -> list:
        """Apply the catalog's placement boundary to capacity accounting.

        Capacity preview and reservation must count the same nodes the
        OpenShift provisioner may select for a seat. Otherwise an unqualified
        or recently recovered worker can make an aggregate preview pass before
        seat provisioning fails closed.
        """
        required_labels = {
            str(key): str(value)
            for key, value in (
                metadata.get("workshop_node_required_labels", {}) or {}
            ).items()
        }
        min_ready_seconds = max(
            0, int(metadata.get("workshop_node_min_ready_seconds", 0))
        )
        eligible = []
        for node in cls._workshop_schedulable_nodes(nodes):
            labels = getattr(getattr(node, "metadata", None), "labels", None) or {}
            if any(labels.get(key) != value for key, value in required_labels.items()):
                continue

            conditions = {
                str(getattr(condition, "type", "")): condition
                for condition in (
                    getattr(getattr(node, "status", None), "conditions", None) or []
                )
            }
            if any(
                str(getattr(conditions.get(kind), "status", "False")) == "True"
                for kind in ("MemoryPressure", "DiskPressure", "PIDPressure")
            ):
                continue
            ready = conditions.get("Ready")
            transition = getattr(ready, "last_transition_time", None)
            if (
                min_ready_seconds
                and transition is not None
                and time.time() - transition.timestamp() < min_ready_seconds
            ):
                continue
            eligible.append(node)
        return eligible

    @staticmethod
    def _pods_using_nodes(pods: list, node_names: set[str]) -> list:
        """Count demand on eligible nodes plus pending unscheduled demand."""
        selected = []
        for pod in pods:
            node_name = getattr(getattr(pod, "spec", None), "node_name", None)
            if not node_name or str(node_name) in node_names:
                selected.append(pod)
        return selected

    def get_cluster_fleet_health(self, *, include_disabled: bool = False) -> list[dict]:
        if not self.cluster_registry or not self.cluster_client_factory:
            return []
        active_states = {"requested", "provisioning", "validating", "ready", "active", "resetting"}
        results = []
        targets = (
            self.cluster_registry.list_all()
            if include_disabled
            else self.cluster_registry.list_enabled()
        )
        for target in targets:
            sessions = [s for s in self._sessions.values() if s.cluster_ref == target.cluster_id and s.status.value in active_states]
            workshops = [w for w in self._workshops.values() if w.cluster_ref == target.cluster_id and w.status.value not in {"completed", "completed_with_errors", "failed"}]
            try:
                clients = self.cluster_client_factory.clients(
                    target.cluster_id,
                    allow_disabled=include_disabled and not target.enabled,
                )
                core = clients.core
                nodes = self._workshop_schedulable_nodes(core.list_node().items)
                node_names = {str(node.metadata.name) for node in nodes}
                pods = self._pods_using_nodes(
                    [
                        p for p in core.list_pod_for_all_namespaces().items
                        if p.status.phase not in ("Succeeded", "Failed")
                    ],
                    node_names,
                )
                cpu = sum(self._cpu_millicores((n.status.allocatable or {}).get("cpu")) for n in nodes)
                memory = sum(self._memory_mib((n.status.allocatable or {}).get("memory")) for n in nodes)
                pod_slots = sum(int((n.status.allocatable or {}).get("pods", 0)) for n in nodes)
                used_cpu = used_memory = 0
                for pod in pods:
                    for container in pod.spec.containers or []:
                        requests = container.resources.requests or {}
                        used_cpu += self._cpu_millicores(requests.get("cpu"))
                        used_memory += self._memory_mib(requests.get("memory"))
                results.append({
                    "cluster_id": target.cluster_id,
                    "cluster_name": target.display_name,
                    "health_status": "healthy" if nodes else "degraded",
                    "healthy": bool(nodes),
                    "eligible": bool(nodes) and target.enabled,
                    "reason": (
                        "eligible"
                        if nodes and target.enabled
                        else "inspection passed; placement remains disabled"
                        if nodes
                        else "no schedulable Ready worker nodes"
                    ),
                    "configured_enabled": target.enabled,
                    "inspection_only": not target.enabled,
                    "available_cpu_millicores": max(0, cpu - used_cpu),
                    "available_memory_mib": max(0, memory - used_memory),
                    "available_pods": max(0, pod_slots - len(pods)),
                    "active_sessions": len(sessions),
                    "active_workshops": len(workshops),
                    "active_seats": sum(len(w.session_ids) for w in workshops),
                    "capabilities": target.capabilities,
                    "ingress_domain": target.ingress_domain,
                })
            except Exception as exc:
                results.append({
                    "cluster_id": target.cluster_id,
                    "cluster_name": target.display_name,
                    "health_status": "unreachable",
                    "healthy": False,
                    "eligible": False,
                    "reason": str(exc),
                    "configured_enabled": target.enabled,
                    "inspection_only": not target.enabled,
                    "available_cpu_millicores": 0,
                    "available_memory_mib": 0,
                    "available_pods": 0,
                    "active_sessions": len(sessions),
                    "active_workshops": len(workshops),
                    "active_seats": sum(len(w.session_ids) for w in workshops),
                    "capabilities": target.capabilities,
                    "ingress_domain": target.ingress_domain,
                })
        return results

    def check_workshop_capacity(self, workshop: Workshop) -> tuple:
        mode = os.environ.get("LAUNCHPAD_MODE", "mock")
        if mode == "mock":
            return True, "mock mode — capacity checks skipped"

        try:
            if workshop.cluster_ref and self.cluster_client_factory:
                v1 = self._target_clients(workshop.cluster_ref).core
            else:
                from kubernetes import client, config
                try:
                    config.load_incluster_config()
                except Exception:
                    config.load_kube_config()
                v1 = client.CoreV1Api()
            capacity = self._workshop_capacity(v1, workshop)
            max_seats = capacity["max_seats"]

            if workshop.num_users <= max_seats:
                return True, (
                    f"Cluster can support {max_seats} seats "
                    f"(CPU: {capacity['max_by_cpu']}, Memory: {capacity['max_by_mem']}, "
                    f"Pods: {capacity['max_by_pods']}; Eligible nodes: "
                    f"{capacity['eligible_nodes']}; {capacity['headroom_pct']}% headroom)"
                )
            else:
                return False, (
                    f"Requested {workshop.num_users} seats but cluster supports {max_seats} "
                    f"(CPU: {capacity['max_by_cpu']}, Memory: {capacity['max_by_mem']}, "
                    f"Pods: {capacity['max_by_pods']}; Eligible nodes: "
                    f"{capacity['eligible_nodes']})"
                )
        except ImportError:
            return False, "kubernetes package not available — capacity cannot be verified"
        except Exception as e:
            logger.warning("Capacity check failed closed: %s", e)
            return False, f"Capacity check failed: {e}"

    def _estimate_max_seats(self, workshop: Workshop) -> int:
        try:
            if workshop.cluster_ref and self.cluster_client_factory:
                v1 = self._target_clients(workshop.cluster_ref).core
            else:
                from kubernetes import client, config
                try:
                    config.load_incluster_config()
                except Exception:
                    config.load_kube_config()
                v1 = client.CoreV1Api()
            return self._workshop_capacity(v1, workshop)["max_seats"]
        except Exception:
            return 0

    @staticmethod
    def _cpu_millicores(value) -> int:
        value = str(value or "0")
        if value.endswith("m"):
            return int(value[:-1])
        if value.endswith("n"):
            return int(value[:-1]) // 1_000_000
        return int(float(value) * 1000)

    @staticmethod
    def _memory_mib(value) -> int:
        value = str(value or "0")
        units = {"Ki": 1 / 1024, "Mi": 1, "Gi": 1024, "Ti": 1024 * 1024}
        for suffix, multiplier in units.items():
            if value.endswith(suffix):
                return int(float(value[:-len(suffix)]) * multiplier)
        return int(value) // (1024 * 1024)

    @staticmethod
    def _workshop_resource_estimate(metadata: dict, seats: int) -> dict:
        """Return the steady plus bounded-burst reservation for a workshop.

        Existing catalog items remain compatible: when the optional shared and
        transient fields are absent, this is the original per-seat
        multiplication. Transient resources are reserved only for the number
        of seats that may provision concurrently, rather than for every seat.
        """
        seats = max(0, int(seats))
        concurrency = max(
            1,
            int(
                metadata.get(
                    "workshop_provision_concurrency",
                    os.environ.get("WORKSHOP_PROVISION_CONCURRENCY", "5"),
                )
            ),
        )
        concurrent_seats = min(seats, concurrency)

        per_seat = {
            "cpu_millicores": int(
                metadata.get(
                    "seat_cpu_millicores",
                    os.environ.get("WORKSHOP_SEAT_CPU_MILLICORES", "1000"),
                )
            ),
            "memory_mib": int(
                metadata.get(
                    "seat_memory_mib",
                    os.environ.get("WORKSHOP_SEAT_MEMORY_MI", "2048"),
                )
            ),
            "pods": int(metadata.get("seat_pods", 1)),
        }
        shared = {
            "cpu_millicores": int(metadata.get("workshop_shared_cpu_millicores", 0)),
            "memory_mib": int(metadata.get("workshop_shared_memory_mib", 0)),
            "pods": int(metadata.get("workshop_shared_pods", 0)),
        }
        if seats == 0:
            shared = {key: 0 for key in shared}
        transient_per_seat = {
            "cpu_millicores": int(metadata.get("seat_transient_cpu_millicores", 0)),
            "memory_mib": int(metadata.get("seat_transient_memory_mib", 0)),
            "pods": int(metadata.get("seat_transient_pods", 0)),
        }
        transient = {
            "concurrent_seats": concurrent_seats,
            **{
                key: value * concurrent_seats
                for key, value in transient_per_seat.items()
            },
        }
        totals = {
            key: shared[key] + per_seat[key] * seats + transient[key]
            for key in ("cpu_millicores", "memory_mib", "pods")
        }
        return {
            **totals,
            "shared": shared,
            "per_seat": per_seat,
            "transient": transient,
        }

    @staticmethod
    def _max_seats_for_resource(
        available: int,
        *,
        shared: int,
        per_seat: int,
        transient_per_seat: int,
        concurrency: int,
    ) -> int:
        """Solve shared + steady seats + a bounded concurrent rollout burst."""
        available = max(0, int(available))
        shared = max(0, int(shared))
        per_seat = max(0, int(per_seat))
        transient_per_seat = max(0, int(transient_per_seat))
        concurrency = max(1, int(concurrency))

        first_wave_cost = per_seat + transient_per_seat
        if available < shared + first_wave_cost:
            return 0
        if first_wave_cost == 0:
            return 999

        seats_in_first_wave = min(
            concurrency, (available - shared) // first_wave_cost
        )
        if seats_in_first_wave < concurrency:
            return seats_in_first_wave
        if per_seat == 0:
            return 999

        first_wave_total = shared + concurrency * first_wave_cost
        return concurrency + (available - first_wave_total) // per_seat

    def _workshop_capacity(self, v1, workshop: Workshop) -> dict:
        total_cpu_m = total_mem_mi = total_pods = 0
        item = self.catalog.get_item(workshop.catalog_item_id)
        metadata = item.metadata if item else {}
        nodes = self._workshop_catalog_nodes(v1.list_node().items, metadata)
        node_names = {str(node.metadata.name) for node in nodes}
        for node in nodes:
            alloc = node.status.allocatable or {}
            total_cpu_m += self._cpu_millicores(alloc.get("cpu"))
            total_mem_mi += self._memory_mib(alloc.get("memory"))
            total_pods += int(alloc.get("pods", 0))

        requested_cpu_m = requested_mem_mi = active_pods = 0
        active = [
            pod for pod in v1.list_pod_for_all_namespaces().items
            if pod.status.phase not in ("Succeeded", "Failed")
        ]
        for pod in self._pods_using_nodes(active, node_names):
            active_pods += 1
            for container in pod.spec.containers or []:
                requests = container.resources.requests or {}
                requested_cpu_m += self._cpu_millicores(requests.get("cpu"))
                requested_mem_mi += self._memory_mib(requests.get("memory"))

        headroom_pct = float(os.environ.get("WORKSHOP_CAPACITY_HEADROOM_PCT", "20"))
        fraction = 1 - headroom_pct / 100
        available_cpu = max(0, int(total_cpu_m * fraction) - requested_cpu_m)
        available_mem = max(0, int(total_mem_mi * fraction) - requested_mem_mi)
        available_pods = max(0, int(total_pods * fraction) - active_pods)
        # Workshop metadata is requester-controlled, so it must never waive
        # shared capacity. A future shared-workload lifecycle can pass trusted
        # persisted reservation state through an internal interface.
        estimate = self._workshop_resource_estimate(metadata, 1)
        concurrency = max(
            1,
            int(
                metadata.get(
                    "workshop_provision_concurrency",
                    os.environ.get("WORKSHOP_PROVISION_CONCURRENCY", "5"),
                )
            ),
        )

        def max_for(resource: str, available: int) -> int:
            shared = estimate["shared"][resource]
            per_seat = estimate["per_seat"][resource]
            transient = int(metadata.get(f"seat_transient_{resource}", 0))
            return self._max_seats_for_resource(
                available,
                shared=shared,
                per_seat=per_seat,
                transient_per_seat=transient,
                concurrency=concurrency,
            )

        max_by_cpu = max_for("cpu_millicores", available_cpu)
        max_by_mem = max_for("memory_mib", available_mem)
        max_by_pods = max_for("pods", available_pods)
        return {
            "max_seats": min(max_by_cpu, max_by_mem, max_by_pods),
            "max_by_cpu": max_by_cpu,
            "max_by_mem": max_by_mem,
            "max_by_pods": max_by_pods,
            "eligible_nodes": len(nodes),
            "headroom_pct": headroom_pct,
        }

    def reclaim_workshop(self, workshop_id: str) -> Workshop:
        provision_event = self._workshop_provision_events.get(workshop_id)
        if provision_event and not provision_event.is_set():
            wait_timeout = max(
                1, int(os.environ.get("WORKSHOP_CANCEL_WAIT_TIMEOUT", "900"))
            )
            if not provision_event.wait(timeout=wait_timeout):
                raise TimeoutError(
                    f"Workshop {workshop_id} provisioning did not stop within "
                    f"{wait_timeout}s"
                )
        workshop = self._workshops.get(workshop_id)
        if not workshop:
            raise ValueError(f"Workshop {workshop_id} not found")

        # A reclaim can be queued while seat workers are still validating. A
        # failed worker persists its session but does not add that session to
        # workshop.session_ids. Rebuild the links after the provisioning event
        # has stopped so group reclaim cannot strand failed-seat resources.
        workshop = self._link_persisted_workshop_sessions(workshop)
        self._save_workshop(workshop)

        failed_reclaims = []
        seats_by_session = {
            seat.session_id: index
            for index, seat in enumerate(workshop.seats)
            if seat.session_id
        }
        for session_id in workshop.session_ids:
            seat_index = seats_by_session.get(session_id)
            if seat_index is not None:
                workshop.seats[seat_index] = workshop.seats[seat_index].model_copy(update={
                    "status": WorkshopSeatStatus.RECLAIMING,
                    "updated_at": datetime.utcnow(),
                })
        self._save_workshop(workshop)

        concurrency = max(
            1, int(os.environ.get("WORKSHOP_RECLAIM_CONCURRENCY", "10"))
        )
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(self._reclaim_workshop_session, session_id): session_id
                for session_id in workshop.session_ids
            }
            for future in as_completed(futures):
                session_id = futures[future]
                seat_index = seats_by_session.get(session_id)
                error = future.result()
                if error:
                    failed_reclaims.append({"session_id": session_id, "error": error})
                if seat_index is not None:
                    workshop.seats[seat_index] = workshop.seats[seat_index].model_copy(update={
                        "status": (
                            WorkshopSeatStatus.FAILED
                            if error
                            else WorkshopSeatStatus.RECLAIMED
                        ),
                        "error": error,
                        "updated_at": datetime.utcnow(),
                    })
                    self._save_workshop(workshop)

        status = (
            WorkshopStatus.COMPLETED
            if not failed_reclaims
            else WorkshopStatus.COMPLETED_WITH_ERRORS
        )
        # A queued seat cancelled before it creates a session has no cluster
        # resources to delete, but it is still part of the reclaimed order.
        # Do not leave a completed workshop displaying pending/provisioning
        # seats after a successful group reclaim.
        for index, seat in enumerate(workshop.seats):
            if not seat.session_id and seat.status in {
                WorkshopSeatStatus.PENDING,
                WorkshopSeatStatus.PROVISIONING,
                WorkshopSeatStatus.RECLAIMING,
            }:
                workshop.seats[index] = seat.model_copy(
                    update={
                        "status": WorkshopSeatStatus.RECLAIMED,
                        "error": None,
                        "updated_at": datetime.utcnow(),
                    }
                )
        workshop = workshop.model_copy(update={
            "status": status,
            "completed_at": datetime.utcnow(),
            "metadata": {**workshop.metadata, "failed_reclaims": failed_reclaims},
        })
        self._save_workshop(workshop)
        access = getattr(self, "public_access_service", None)
        if access:
            access.expire_order(workshop_id)
        return workshop

    def _reclaim_workshop_session(self, session_id: str) -> Optional[str]:
        existing = self._sessions.get(session_id)
        if existing and existing.status == SessionStatus.RECLAIMED:
            return None
        try:
            reclaimed_session = self.reclaim_session(session_id)
            if reclaimed_session.status == SessionStatus.CLEANUP_FAILED:
                reclaimed_session = self.force_reclaim_session(
                    session_id, require_cleanup_success=True
                )
            if reclaimed_session.status != SessionStatus.RECLAIMED:
                return reclaimed_session.lifecycle_events[-1].reason
            return None
        except Exception as initial_exc:
            try:
                reclaimed_session = self.force_reclaim_session(
                    session_id, require_cleanup_success=True
                )
                if reclaimed_session.status != SessionStatus.RECLAIMED:
                    return reclaimed_session.lifecycle_events[-1].reason
                return None
            except Exception as exc:
                return f"{initial_exc}; force-reclaim failed: {exc}"

    def queue_workshop_reclaim(self, workshop_id: str) -> Workshop:
        workshop = self._workshops.get(workshop_id)
        if not workshop:
            raise ValueError(f"Workshop {workshop_id} not found")
        if workshop.status == WorkshopStatus.RECLAIMING:
            return workshop
        if workshop.status == WorkshopStatus.COMPLETED:
            seats = [
                seat.model_copy(
                    update={
                        "status": WorkshopSeatStatus.RECLAIMED,
                        "error": None,
                        "updated_at": datetime.utcnow(),
                    }
                )
                if not seat.session_id
                and seat.status
                in {
                    WorkshopSeatStatus.PENDING,
                    WorkshopSeatStatus.PROVISIONING,
                    WorkshopSeatStatus.RECLAIMING,
                }
                else seat
                for seat in workshop.seats
            ]
            if seats != workshop.seats:
                workshop = workshop.model_copy(update={"seats": seats})
                self._save_workshop(workshop)
            return workshop

        workshop = self._link_persisted_workshop_sessions(workshop)

        seats = [
            seat.model_copy(update={
                "status": WorkshopSeatStatus.RECLAIMING,
                "error": None,
                "updated_at": datetime.utcnow(),
            }) if seat.session_id else seat
            for seat in workshop.seats
        ]
        queued = workshop.model_copy(update={
            "status": WorkshopStatus.RECLAIMING,
            "seats": seats,
        })
        self._save_workshop(queued)
        return queued

    def get_workshop(self, workshop_id: str) -> Optional[Workshop]:
        return self._workshops.get(workshop_id)

    def _public_access_session(self, order_id: str, seat_ref: str) -> Optional[LabSession]:
        workshop = self._workshops.get(order_id)
        if workshop:
            seat = next((item for item in workshop.seats if item.seat_id == seat_ref), None)
            return self._sessions.get(seat.session_id) if seat and seat.session_id else None
        return next((item for item in self._sessions.values() if item.request_id == order_id), None)

    def bind_public_participant(self, order_id: str, seat_ref: str, username: str) -> None:
        """Grant the stable OIDC user edit access only to the claimed namespace."""
        session = self._public_access_session(order_id, seat_ref)
        if not session or not session.namespace:
            raise ValueError("Claimed environment is not ready")
        clients = self._target_clients(session.cluster_ref)
        if not clients:
            if os.environ.get("LAUNCHPAD_MODE", "mock") == "mock":
                return
            raise ValueError("Target cluster credentials are unavailable")
        from kubernetes import client
        name = f"launchpad-participant-{hashlib.sha256(username.encode()).hexdigest()[:12]}"
        role_bindings = [(name, "edit")]
        if session.catalog_item_id == "agentops-observability":
            role_bindings.append((f"{name}-logs", "cluster-logging-application-view"))
        for binding_name, cluster_role in role_bindings:
            binding = client.V1RoleBinding(
                metadata=client.V1ObjectMeta(
                    name=binding_name,
                    labels={
                        "launchpad.redhat.com/order-id": order_id,
                        "launchpad.redhat.com/managed": "true",
                    },
                ),
                role_ref=client.V1RoleRef(
                    api_group="rbac.authorization.k8s.io",
                    kind="ClusterRole",
                    name=cluster_role,
                ),
                subjects=[
                    client.RbacV1Subject(
                        api_group="rbac.authorization.k8s.io",
                        kind="User",
                        name=username,
                    )
                ],
            )
            try:
                clients.rbac.create_namespaced_role_binding(session.namespace, binding)
            except client.ApiException as exc:
                if exc.status != 409:
                    raise ValueError(
                        f"Failed to grant participant namespace access: {exc.reason}"
                    ) from exc

    def unbind_public_participant(self, order_id: str, seat_ref: str, username: str) -> None:
        session = self._public_access_session(order_id, seat_ref)
        clients = self._target_clients(session.cluster_ref) if session else None
        if not session or not session.namespace or not clients:
            return
        from kubernetes import client
        name = f"launchpad-participant-{hashlib.sha256(username.encode()).hexdigest()[:12]}"
        binding_names = [name]
        if session.catalog_item_id == "agentops-observability":
            binding_names.append(f"{name}-logs")
        for binding_name in binding_names:
            try:
                clients.rbac.delete_namespaced_role_binding(
                    binding_name,
                    session.namespace,
                )
            except client.ApiException as exc:
                if exc.status != 404:
                    raise ValueError(
                        f"Failed to revoke participant namespace access: {exc.reason}"
                    ) from exc

    def enforce_ttl(self) -> int:
        now = datetime.utcnow()
        reclaimable = {"ready", "active"}
        reclaimed_count = 0
        expired = [
            session
            for session in list(self._sessions.values())
            if session.status.value in reclaimable
            and session.expires_at is not None
            and session.expires_at < now
        ]
        workshop_expirations: dict[str, list[LabSession]] = {}
        standalone_expirations: list[LabSession] = []
        terminal_workshop_states = {
            WorkshopStatus.COMPLETED,
            WorkshopStatus.COMPLETED_WITH_ERRORS,
            WorkshopStatus.FAILED,
        }
        for session in expired:
            request = self._requests.get(session.request_id)
            workshop_id = (
                request.metadata.get("workshop_id") if request else None
            )
            workshop = self._workshops.get(workshop_id) if workshop_id else None
            if workshop and workshop.status not in terminal_workshop_states:
                workshop_expirations.setdefault(workshop.workshop_id, []).append(
                    session
                )
            else:
                standalone_expirations.append(session)

        # A workshop's first expired seat represents expiry of the order.  The
        # order-level expiry written during provisioning makes those timestamps
        # identical for new workshops; grouping also repairs older staggered
        # records without leaving the parent falsely marked READY.
        for workshop_id in workshop_expirations:
            workshop = self._workshops[workshop_id]
            active_session_ids = {
                session_id
                for session_id in workshop.session_ids
                if (session := self._sessions.get(session_id)) is not None
                and session.status.value in reclaimable
            }
            try:
                self.queue_workshop_reclaim(workshop_id)
                self.reclaim_workshop(workshop_id)
            except Exception as exc:
                logger.error(
                    "TTL reclaim failed for workshop %s: %s",
                    workshop_id,
                    exc,
                )
            reclaimed_count += sum(
                1
                for session_id in active_session_ids
                if (session := self._sessions.get(session_id)) is not None
                and session.status == SessionStatus.RECLAIMED
            )

        for session in standalone_expirations:
            try:
                self.reclaim_session(session.session_id)
                reclaimed_count += 1
            except Exception as e:
                logger.warning(
                    "TTL reclaim failed for session %s, attempting force-reclaim: %s",
                    session.session_id,
                    e,
                )
                try:
                    self.force_reclaim_session(session.session_id)
                    reclaimed_count += 1
                except Exception as e2:
                    logger.error(
                        "Force-reclaim also failed for session %s: %s",
                        session.session_id,
                        e2,
                    )
        return reclaimed_count
