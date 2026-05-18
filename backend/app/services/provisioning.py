from __future__ import annotations

import uuid as _uuid
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
from app.domain.enums import LabRequestStatus, SessionStatus
from app.domain.lifecycle import transition
from app.domain.models import (
    LabRequest,
    LabSession,
    LifecycleEvent,
    ProvisioningPlan,
    ShowbackRecord,
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

        self._requests: dict[str, LabRequest] = {}
        self._sessions: dict[str, LabSession] = {}
        self._plans: dict[str, ProvisioningPlan] = {}

    def submit_request(self, request: LabRequest) -> LabRequest:
        catalog_item = self.catalog.get_item(request.catalog_item_id)
        if not catalog_item:
            request = request.model_copy(update={"status": LabRequestStatus.REJECTED})
            self._requests[request.request_id] = request
            return request

        constraint_result: ConstraintResult = self.constraints.evaluate(request)
        if not constraint_result.allowed:
            request = request.model_copy(update={"status": LabRequestStatus.REJECTED})
            self._requests[request.request_id] = request
            return request

        request = request.model_copy(update={"status": LabRequestStatus.ACCEPTED})
        self._requests[request.request_id] = request
        return request

    def provision(self, request_id: str) -> LabSession:
        request = self._requests.get(request_id)
        if not request:
            raise ValueError(f"Request {request_id} not found")
        if request.status != LabRequestStatus.ACCEPTED:
            raise ValueError(f"Request {request_id} is not accepted (status: {request.status.value})")

        catalog_item = self.catalog.get_item(request.catalog_item_id)
        if not catalog_item:
            raise ValueError(f"Catalog item {request.catalog_item_id} not found")

        hw = request.hardware_profile or catalog_item.default_hardware_profile or "xeon-basic"
        qp = request.quota_profile or catalog_item.default_quota_profile or "standard"
        if not self.pool.check_capacity(hw, qp):
            raise ValueError(f"No capacity available for hardware={hw} quota={qp}")
        self.pool.reserve(request.request_id, hw, qp)

        plan = self.provisioner.create_plan(request, catalog_item)
        self._plans[plan.plan_id] = plan

        result = self.provisioner.provision(plan)

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

        maas_api_key = f"sk-launchpad-{_uuid.uuid4().hex[:24]}"

        session = LabSession(
            request_id=request.request_id,
            tenant_id=request.tenant_id,
            catalog_item_id=request.catalog_item_id,
            namespace=result.namespace,
            lab_url=result.lab_url,
            dashboard_url=dashboard_url,
            expires_at=expires_at,
            resources=result.resources,
            maas_api_key=maas_api_key,
        )

        session = transition(session, SessionStatus.PROVISIONING, reason="provisioning started")
        session = transition(session, SessionStatus.VALIDATING, reason="provisioning complete")

        self._sessions[session.session_id] = session
        self._requests[request_id] = request.model_copy(
            update={"status": LabRequestStatus.PROVISIONING}
        )

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

        self._sessions[session_id] = session
        return session

    def activate_session(self, session_id: str) -> LabSession:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        session = transition(session, SessionStatus.ACTIVE, reason="lab activated")
        self._sessions[session_id] = session
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
        self._sessions[session_id] = session
        return session

    def reclaim_session(self, session_id: str) -> LabSession:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        self.pool.release(session.request_id)
        if self.cleanup and session.resources.get("compose_file"):
            self.cleanup.cleanup(session.resources["compose_file"])
        session = transition(session, SessionStatus.RECLAIMED, reason="resources reclaimed")
        self._sessions[session_id] = session
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
        event = LifecycleEvent(
            from_status=session.status,
            to_status=SessionStatus.RECLAIMED,
            reason="force reclaimed by admin",
        )
        session = session.model_copy(
            update={
                "status": SessionStatus.RECLAIMED,
                "completed_at": datetime.utcnow(),
                "lifecycle_events": session.lifecycle_events + [event],
            }
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[LabSession]:
        return self._sessions.get(session_id)

    def get_request(self, request_id: str) -> Optional[LabRequest]:
        return self._requests.get(request_id)
