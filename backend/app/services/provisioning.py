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

from app.integrations.event_publisher import publish_event as notify_stargate

from app.adapters.interfaces import ConstraintResult
from app.adapters.mock.branding import FileBrandingAdapter
from app.adapters.mock.catalog import MockCatalogAdapter
from app.adapters.mock.constraints import MockConstraintAdapter
from app.adapters.mock.observability import MockObservabilityAdapter
from app.adapters.mock.pool import MockPoolAdapter
from app.adapters.mock.provisioning import MockProvisioningAdapter
from app.adapters.mock.showback import MockShowbackAdapter
from app.adapters.mock.validation import MockValidationAdapter
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
from app.domain.access import ExposurePolicy
from app.domain.reports import HandoffPackage, RepeatabilityReport, SecurityPlan

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
        return self.cluster_client_factory.clients(cluster_ref)

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
                        target=self.cluster_registry.get(cluster_ref),
                    )
                return OpenShiftSandboxProvisioner()
            elif mode == "local":
                from app.adapters.local.sandbox_provisioner import LocalSandboxProvisioner
                return LocalSandboxProvisioner()
        if mode == "openshift" and cluster_ref and self.cluster_registry:
            from app.adapters.openshift.provisioning import OpenShiftProvisioningAdapter
            target = self.cluster_registry.get(cluster_ref)
            clients = self._target_clients(cluster_ref)
            control_clients = self._target_clients("oberon")
            return OpenShiftProvisioningAdapter(
                clients=clients,
                target=target,
                argocd_custom_objects=control_clients.custom if control_clients else None,
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
            control_clients = self._target_clients("oberon")
            return OpenShiftCleanupAdapter(
                clients=self._target_clients(cluster_ref),
                argocd_custom_objects=control_clients.custom if control_clients else None,
            )
        return self.cleanup

    def _select_target_cluster(self, request: LabRequest, catalog_item) -> Optional[str]:
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
        )
        return target.cluster_id

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

    def provision(self, request_id: str, workshop_id: str = None) -> LabSession:
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

        if self.preflight:
            preflight_result = self.preflight.check(catalog_item)
            if not preflight_result.passed:
                failed = [c for c in preflight_result.checks if c.status == "fail"]
                reasons = "; ".join(c.message for c in failed)
                raise ValueError(f"Preflight failed for {catalog_item.catalog_item_id}: {reasons}")

        hw, qp = self._resolve_hardware(request, catalog_item)
        preferred_cluster = self._select_target_cluster(request, catalog_item)
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
                "maas_api_key": maas_api_key,
                "sandbox_data": sandbox_data,
            }
        })
        self._save_plan(plan)

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

        catalog_item = self.catalog.get_item(session.catalog_item_id)
        version = catalog_item.version if catalog_item else "unknown"

        validation_passed = (
            len(session.validation_results) > 0
            and all(r.result.value != "fail" for r in session.validation_results)
        )

        return RepeatabilityReport(
            session_id=session.session_id,
            catalog_item_id=session.catalog_item_id,
            version=version,
            catalog_versioned=catalog_item is not None,
            provisioning_plan_generated=plan is not None,
            validation_passed=validation_passed,
            handoff_generated=session.status in (SessionStatus.READY, SessionStatus.ACTIVE),
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
        }
        return hashlib.sha256(json.dumps(order, sort_keys=True).encode()).hexdigest()

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

    def preview_workshop_capacity(self, workshop: Workshop) -> dict:
        catalog_item = self.catalog.get_item(workshop.catalog_item_id)
        selected_cluster = workshop.cluster_ref or workshop.target_cluster
        if self.cluster_registry and catalog_item:
            try:
                selected_cluster = self.cluster_registry.select(
                    required_capabilities=catalog_item.required_capabilities,
                    required_models=(catalog_item.metadata or {}).get("required_models", []),
                    override=workshop.target_cluster,
                    require_public_access=workshop.exposure_policy == ExposurePolicy.PUBLIC_CODE,
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
        cpu_per_seat = int(metadata.get(
            "seat_cpu_millicores",
            os.environ.get("WORKSHOP_SEAT_CPU_MILLICORES", "1000"),
        ))
        memory_per_seat = int(metadata.get(
            "seat_memory_mib",
            os.environ.get("WORKSHOP_SEAT_MEMORY_MI", "2048"),
        ))
        pods_per_seat = int(metadata.get("seat_pods", 1))
        return {
            "can_provision": can_provision,
            "reason": reason,
            "selected_cluster": selected_cluster,
            "placement_reason": (
                f"Entire workshop assigned to {selected_cluster}; seats will not be split"
                if selected_cluster else "single-cluster placement"
            ),
            "seats_requested": workshop.num_users,
            "estimated_resources": {
                "cpu_millicores": cpu_per_seat * workshop.num_users,
                "memory_mib": memory_per_seat * workshop.num_users,
                "pods": pods_per_seat * workshop.num_users,
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
        deadline = time.monotonic() + timeout
        consecutive_passes = 0
        failures: dict[int, str] = {}

        while time.monotonic() < deadline:
            failures = {}

            def check_endpoint(item: tuple[int, str]) -> tuple[int, str | None]:
                seat_number, url = item
                try:
                    response = requests.get(url, timeout=10, verify=False)
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
        workshop_limit = int(os.environ.get(
            "MAX_ACTIVE_SESSIONS_PER_WORKSHOP", str(self.MAX_ACTIVE_PER_WORKSHOP)
        ))
        if workshop.num_users > workshop_limit:
            raise ValueError(
                f"Workshop seat count exceeds the supported limit of {workshop_limit}"
            )
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
        queued = workshop.model_copy(update={"status": WorkshopStatus.QUEUED, "seats": seats})
        self._save_workshop(queued)
        return queued

    def provision_workshop(
        self, workshop: Workshop, idempotency_key: str = None
    ) -> Workshop:
        provision_event = self._workshop_provision_events.setdefault(
            workshop.workshop_id, threading.Event()
        )
        provision_event.clear()
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

        if self.preflight:
            preflight_result = self.preflight.check(catalog_item)
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
            if seat.session_id and self._sessions.get(seat.session_id):
                workshop.seats[i] = seat.model_copy(update={
                    "status": WorkshopSeatStatus.READY,
                    "error": None,
                    "updated_at": datetime.utcnow(),
                })
                session_ids.append(seat.session_id)
                continue
            workshop.seats[i] = seat.model_copy(update={
                "status": WorkshopSeatStatus.PROVISIONING,
                "updated_at": datetime.utcnow(),
            })
            pending_indexes.append(i)
        self._save_workshop(workshop)

        concurrency = max(
            1, int(os.environ.get("WORKSHOP_PROVISION_CONCURRENCY", "5"))
        )
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(self._provision_workshop_seat, workshop, i): i
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

        current = self._workshops.get(workshop.workshop_id)
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
                accepted.request_id, workshop_id=workshop.workshop_id
            )
            session = session.model_copy(update={
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

    def get_cluster_fleet_health(self) -> list[dict]:
        if not self.cluster_registry or not self.cluster_client_factory:
            return []
        active_states = {"requested", "provisioning", "validating", "ready", "active", "resetting"}
        results = []
        for target in self.cluster_registry.list_enabled():
            sessions = [s for s in self._sessions.values() if s.cluster_ref == target.cluster_id and s.status.value in active_states]
            workshops = [w for w in self._workshops.values() if w.cluster_ref == target.cluster_id and w.status.value not in {"completed", "completed_with_errors", "failed"}]
            try:
                core = self._target_clients(target.cluster_id).core
                nodes = core.list_node().items
                pods = [p for p in core.list_pod_for_all_namespaces().items if p.status.phase not in ("Succeeded", "Failed")]
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
                    "health_status": "healthy",
                    "healthy": True,
                    "eligible": True,
                    "reason": "eligible",
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
                    f"Pods: {capacity['max_by_pods']}; {capacity['headroom_pct']}% headroom)"
                )
            else:
                return False, (
                    f"Requested {workshop.num_users} seats but cluster supports {max_seats} "
                    f"(CPU: {capacity['max_by_cpu']}, Memory: {capacity['max_by_mem']}, "
                    f"Pods: {capacity['max_by_pods']})"
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

    def _workshop_capacity(self, v1, workshop: Workshop) -> dict:
        total_cpu_m = total_mem_mi = total_pods = 0
        for node in v1.list_node().items:
            alloc = node.status.allocatable or {}
            total_cpu_m += self._cpu_millicores(alloc.get("cpu"))
            total_mem_mi += self._memory_mib(alloc.get("memory"))
            total_pods += int(alloc.get("pods", 0))

        requested_cpu_m = requested_mem_mi = active_pods = 0
        for pod in v1.list_pod_for_all_namespaces().items:
            if pod.status.phase in ("Succeeded", "Failed"):
                continue
            active_pods += 1
            for container in pod.spec.containers or []:
                requests = container.resources.requests or {}
                requested_cpu_m += self._cpu_millicores(requests.get("cpu"))
                requested_mem_mi += self._memory_mib(requests.get("memory"))

        item = self.catalog.get_item(workshop.catalog_item_id)
        metadata = item.metadata if item else {}
        per_seat_cpu_m = int(metadata.get(
            "seat_cpu_millicores", os.environ.get("WORKSHOP_SEAT_CPU_MILLICORES", "1000")
        ))
        per_seat_mem_mi = int(metadata.get(
            "seat_memory_mib", os.environ.get("WORKSHOP_SEAT_MEMORY_MI", "2048")
        ))
        per_seat_pods = int(metadata.get("seat_pods", 1))
        headroom_pct = float(os.environ.get("WORKSHOP_CAPACITY_HEADROOM_PCT", "20"))
        fraction = 1 - headroom_pct / 100
        available_cpu = max(0, int(total_cpu_m * fraction) - requested_cpu_m)
        available_mem = max(0, int(total_mem_mi * fraction) - requested_mem_mi)
        available_pods = max(0, int(total_pods * fraction) - active_pods)
        max_by_cpu = available_cpu // per_seat_cpu_m if per_seat_cpu_m else 999
        max_by_mem = available_mem // per_seat_mem_mi if per_seat_mem_mi else 999
        max_by_pods = available_pods // per_seat_pods if per_seat_pods else 999
        return {
            "max_seats": min(max_by_cpu, max_by_mem, max_by_pods),
            "max_by_cpu": max_by_cpu,
            "max_by_mem": max_by_mem,
            "max_by_pods": max_by_pods,
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
        if workshop.status in {
            WorkshopStatus.COMPLETED,
            WorkshopStatus.COMPLETED_WITH_ERRORS,
        }:
            return workshop

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

    def enforce_ttl(self) -> int:
        now = datetime.utcnow()
        reclaimable = {"ready", "active"}
        reclaimed_count = 0
        for session in list(self._sessions.values()):
            if session.status.value not in reclaimable:
                continue
            if session.expires_at is None:
                continue
            if session.expires_at < now:
                try:
                    self.reclaim_session(session.session_id)
                    reclaimed_count += 1
                except Exception as e:
                    logger.warning("TTL reclaim failed for session %s, attempting force-reclaim: %s", session.session_id, e)
                    try:
                        self.force_reclaim_session(session.session_id)
                        reclaimed_count += 1
                    except Exception as e2:
                        logger.error("Force-reclaim also failed for session %s: %s", session.session_id, e2)
        return reclaimed_count
