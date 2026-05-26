from __future__ import annotations

import os
import threading
import uuid as _uuid
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
from app.domain.enums import CatalogCategory, LabRequestStatus, Persistence, SessionStatus
from app.domain.lifecycle import transition
from app.domain.models import (
    LabRequest,
    LabSession,
    LifecycleEvent,
    ProvisioningPlan,
    ShowbackRecord,
    Workshop,
)
from app.domain.reports import HandoffPackage, RepeatabilityReport, SecurityPlan


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

        self._requests: dict[str, LabRequest] = {}
        self._sessions: dict[str, LabSession] = {}
        self._plans: dict[str, ProvisioningPlan] = {}
        self._workshops: dict[str, Workshop] = {}
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
                        core = client.CoreV1Api()
                        try:
                            core.read_namespace(session.namespace)
                        except Exception:
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
                            self._save_session(session)
                except Exception:
                    pass

    def _get_provisioner(self, catalog_item):
        from app.domain.enums import CatalogCategory

        mode = os.environ.get("LAUNCHPAD_MODE", "mock")
        if mode == "rhdp" and catalog_item.metadata.get("provisioner_mode") == "rhdp":
            from app.adapters.rhdp.provisioning import RHDPProvisioningAdapter
            return RHDPProvisioningAdapter()

        if catalog_item.category == CatalogCategory.OPEN_SANDBOX:
            mode = os.environ.get("LAUNCHPAD_MODE", "mock")
            if mode == "openshift":
                from app.adapters.openshift.sandbox_provisioning import OpenShiftSandboxProvisioner
                return OpenShiftSandboxProvisioner()
            elif mode == "local":
                from app.adapters.local.sandbox_provisioner import LocalSandboxProvisioner
                return LocalSandboxProvisioner()
        return self.provisioner

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

    # Session limits per user/tenant
    MAX_ACTIVE_PER_USER = int(os.environ.get("MAX_ACTIVE_SESSIONS_PER_USER", "2"))
    MAX_ACTIVE_PER_TENANT = int(os.environ.get("MAX_ACTIVE_SESSIONS_PER_TENANT", "5"))

    def _check_session_limits(self, request: LabRequest) -> None:
        active_statuses = {"requested", "provisioning", "validating", "ready", "active"}

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

    def provision(self, request_id: str) -> LabSession:
        request = self._requests.get(request_id)
        if not request:
            raise ValueError(f"Request {request_id} not found")
        if request.status != LabRequestStatus.ACCEPTED:
            raise ValueError(f"Request {request_id} is not accepted (status: {request.status.value})")

        self._check_session_limits(request)

        catalog_item = self.catalog.get_item(request.catalog_item_id)
        if not catalog_item:
            raise ValueError(f"Catalog item {request.catalog_item_id} not found")

        hw = request.hardware_profile or catalog_item.default_hardware_profile or "xeon-basic"
        qp = request.quota_profile or catalog_item.default_quota_profile or "standard"
        if not self.pool.check_capacity(hw, qp):
            raise ValueError(f"No capacity available for hardware={hw} quota={qp}")
        reservation = self.pool.reserve(request.request_id, hw, qp)

        maas_api_key = f"sk-launchpad-{_uuid.uuid4().hex[:24]}"

        provisioner = self._get_provisioner(catalog_item)
        plan = provisioner.create_plan(request, catalog_item)

        sandbox_data = {}
        if isinstance(reservation, dict):
            sandbox_data = reservation

        plan = plan.model_copy(update={
            "required_resources": {
                **plan.required_resources,
                "maas_api_key": maas_api_key,
                "sandbox_data": sandbox_data,
            }
        })
        self._save_plan(plan)

        result = provisioner.provision(plan)

        if request.persistence == Persistence.PERSISTENT:
            expires_at = None
        else:
            ttl_str = request.ttl or catalog_item.default_ttl or "4h"
            hours = int(ttl_str.replace("h", ""))
            expires_at = datetime.utcnow() + timedelta(hours=hours)

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

        session = LabSession(
            request_id=request.request_id,
            tenant_id=request.tenant_id,
            catalog_item_id=request.catalog_item_id,
            namespace=result.namespace,
            cluster_ref=cluster_ref,
            lab_url=result.lab_url,
            dashboard_url=dashboard_url,
            expires_at=expires_at,
            resources=result.resources,
            maas_api_key=maas_api_key,
            metadata={"labels": session_labels},
        )

        session = transition(session, SessionStatus.PROVISIONING, reason="provisioning started")
        session = transition(session, SessionStatus.VALIDATING, reason="provisioning complete")

        self._save_session(session)
        self._save_request(request.model_copy(
            update={"status": LabRequestStatus.PROVISIONING}
        ))

        return session

    def validate_session(self, session_id: str) -> LabSession:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        results = self.validator.validate(session)
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
        return session

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
        self.pool.release(session.request_id)

        cleanup_errors = []
        if self.cleanup and session.resources.get("compose_file"):
            try:
                self.cleanup.cleanup(session.resources["compose_file"])
            except Exception as e:
                cleanup_errors.append(str(e))

        if self.cleanup and session.namespace:
            try:
                self.cleanup.cleanup(session.namespace)
            except Exception as e:
                cleanup_errors.append(str(e))

        if self.cleanup and session.resources.get("gateway_namespace"):
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
                        self.cleanup.cleanup(gw_ns)
                    except Exception as e:
                        cleanup_errors.append(str(e))

        session = self._scrub_credentials(session)

        if cleanup_errors:
            session = transition(session, SessionStatus.CLEANUP_FAILED,
                                 reason=f"cleanup failed — credentials scrubbed — errors: {'; '.join(cleanup_errors)}")
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
            notify_stargate(
                session_id=session.session_id,
                namespace=session.namespace,
                status="reclaimed",
                lab_code=session.catalog_item_id,
                tenant_id=session.tenant_id,
            )
        return session

    def force_reclaim_session(self, session_id: str) -> LabSession:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        self.pool.release(session.request_id)
        if self.cleanup and session.resources.get("compose_file"):
            self.cleanup.cleanup(session.resources["compose_file"])
        if self.cleanup and session.resources.get("container_name"):
            self.cleanup.cleanup(session.resources["container_name"])
        if self.cleanup and session.namespace:
            try:
                self.cleanup.cleanup(session.namespace)
            except Exception:
                pass
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

    def provision_workshop(self, workshop: Workshop) -> Workshop:
        workshop = workshop.model_copy(update={
            "status": "provisioning",
            "started_at": datetime.utcnow(),
        })
        self._workshops[workshop.workshop_id] = workshop

        session_ids = []
        for i in range(workshop.num_users):
            user_id = f"workshop-{workshop.workshop_id[:8]}-user-{i+1}"
            request = LabRequest(
                tenant_id=workshop.tenant_id,
                requester_id=user_id,
                catalog_item_id=workshop.catalog_item_id,
                requested_mode=CatalogCategory.QUICK_START,
                ttl=workshop.ttl,
                metadata={"workshop_id": workshop.workshop_id, "purpose": workshop.purpose},
            )
            accepted = self.submit_request(request)
            if accepted.status != LabRequestStatus.ACCEPTED:
                continue
            try:
                session = self.provision(accepted.request_id)
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
                session_ids.append(session.session_id)
            except ValueError:
                continue

        workshop = workshop.model_copy(update={
            "status": "ready",
            "session_ids": session_ids,
        })
        self._workshops[workshop.workshop_id] = workshop
        return workshop

    def reclaim_workshop(self, workshop_id: str) -> Workshop:
        workshop = self._workshops.get(workshop_id)
        if not workshop:
            raise ValueError(f"Workshop {workshop_id} not found")

        failed_reclaims = []
        for session_id in workshop.session_ids:
            try:
                self.reclaim_session(session_id)
            except (ValueError, Exception):
                try:
                    self.force_reclaim_session(session_id)
                except Exception as e:
                    failed_reclaims.append({"session_id": session_id, "error": str(e)})

        status = "completed" if not failed_reclaims else "completed_with_errors"
        workshop = workshop.model_copy(update={
            "status": status,
            "completed_at": datetime.utcnow(),
            "metadata": {**workshop.metadata, "failed_reclaims": failed_reclaims},
        })
        self._workshops[workshop.workshop_id] = workshop
        return workshop

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
                except Exception:
                    try:
                        self.force_reclaim_session(session.session_id)
                        reclaimed_count += 1
                    except Exception:
                        pass
        return reclaimed_count
