from __future__ import annotations

import os
from types import SimpleNamespace

from app.adapters.mock.branding import FileBrandingAdapter
from app.adapters.mock.catalog import MockCatalogAdapter
from app.domain.models import Tenant
from app.services.provisioning import ProvisioningService
from app.storage.database import get_database_url


class TenantStore:
    def __init__(self, db_store=None) -> None:
        self._tenants: dict[str, Tenant] = {}
        self._db = db_store

    def create(self, tenant: Tenant) -> Tenant:
        self._tenants[tenant.tenant_id] = tenant
        if self._db:
            self._db.save(tenant)
        return tenant

    def get(self, tenant_id: str) -> Tenant | None:
        t = self._tenants.get(tenant_id)
        if not t and self._db:
            t = self._db.get(tenant_id)
            if t:
                self._tenants[tenant_id] = t
        return t

    def list_all(self) -> list[Tenant]:
        if self._db:
            db_tenants = self._db.list_all()
            for t in db_tenants:
                self._tenants[t.tenant_id] = t
        return list(self._tenants.values())


def _create_db_stores():
    if not get_database_url():
        return None
    from app.storage.stores import (
        PostgresCatalogStore,
        PostgresPlanStore,
        PostgresRequestStore,
        PostgresSessionStore,
        PostgresShowbackStore,
        PostgresTenantStore,
        PostgresWorkshopStore,
    )
    return SimpleNamespace(
        tenants=PostgresTenantStore(),
        requests=PostgresRequestStore(),
        sessions=PostgresSessionStore(),
        plans=PostgresPlanStore(),
        showback=PostgresShowbackStore(),
        catalog=PostgresCatalogStore(),
        workshops=PostgresWorkshopStore(),
    )


def _create_catalog():
    catalog_dir = os.environ.get("CATALOG_DIR", "")
    if catalog_dir and os.path.isdir(catalog_dir):
        from app.adapters.file.catalog import FileCatalogAdapter
        local = FileCatalogAdapter(catalog_dir)
    else:
        local = MockCatalogAdapter()

    babylon_kc = os.environ.get("BABYLON_KUBECONFIG", "")
    if babylon_kc and os.path.exists(babylon_kc):
        from app.adapters.rhdp.babylon_catalog import BabylonCatalogAdapter
        from app.adapters.rhdp.combined_catalog import CombinedCatalogAdapter
        babylon = BabylonCatalogAdapter(kubeconfig_path=babylon_kc)
        return CombinedCatalogAdapter(local_catalog=local, babylon_catalog=babylon)
    return local


def create_provisioning_service() -> ProvisioningService:
    mode = os.environ.get("LAUNCHPAD_MODE", "mock")
    db_stores = _create_db_stores()
    catalog = _create_catalog()
    if mode == "local":
        from app.adapters.local.cleanup import LocalCleanupAdapter
        from app.adapters.local.provisioning import LocalProvisioningAdapter
        from app.adapters.local.validation import LocalValidationAdapter
        return ProvisioningService(
            catalog=catalog,
            provisioner=LocalProvisioningAdapter(),
            validator=LocalValidationAdapter(),
            cleanup=LocalCleanupAdapter(),
            db_stores=db_stores,
        )
    elif mode == "openshift":
        from app.adapters.openshift.cleanup import OpenShiftCleanupAdapter
        from app.adapters.openshift.pool import OpenShiftPoolAdapter
        from app.adapters.openshift.provisioning import OpenShiftProvisioningAdapter
        from app.adapters.openshift.validation import OpenShiftValidationAdapter
        from app.adapters.openshift.client_factory import ClusterClientFactory
        from app.services.cluster_registry import ClusterRegistry

        cluster_registry = ClusterRegistry.from_file()
        cluster_client_factory = ClusterClientFactory(cluster_registry)

        preflight = None
        litellm_base = os.environ.get("LITELLM_API_BASE", "")
        if litellm_base:
            from app.adapters.openshift.preflight import LiteLLMPreflightChecker
            preflight = LiteLLMPreflightChecker(
                api_base=litellm_base,
                api_key=os.environ.get("LITELLM_API_KEY", ""),
            )

        maas_key_broker = None
        litellm_master_key = os.environ.get("LITELLM_API_KEY", "")
        if litellm_base and litellm_master_key:
            from app.adapters.openshift.maas_keys import LiteLLMVirtualKeyBroker
            maas_key_broker = LiteLLMVirtualKeyBroker(
                api_base=litellm_base,
                master_key=litellm_master_key,
            )

        classifier = None
        if os.environ.get("WORKLOAD_PROFILING_ENABLED", "false").lower() == "true":
            from app.services.workload_classifier import WorkloadClassifier
            classifier = WorkloadClassifier()

        feedback = None
        if os.environ.get("FEEDBACK_TRACKING_ENABLED", "false").lower() == "true":
            from app.services.feedback_tracker import FeedbackTracker
            outcome_store = None
            if db_stores:
                from app.storage.stores import PostgresOutcomeStore
                outcome_store = PostgresOutcomeStore()
            feedback = FeedbackTracker(db_store=outcome_store)

        placement = None
        if os.environ.get("SMART_PLACEMENT_ENABLED", "true").lower() != "false":
            from app.services.placement import PlacementService
            placement = PlacementService(
                stargate_url=os.environ.get("STARGATE_API_URL", ""),
                stargate_api_key=os.environ.get("STARGATE_API_KEY", ""),
            )

        brain = None
        if os.environ.get("ORCHESTRATION_BRAIN_ENABLED", "false").lower() == "true":
            from app.services.orchestration_brain import OrchestrationBrain
            deepfield = None
            deepfield_url = os.environ.get("DEEPFIELD_API_URL", "")
            if deepfield_url:
                from app.adapters.deepfield.client import DeepFieldAdapter
                deepfield = DeepFieldAdapter(api_url=deepfield_url)
            brain = OrchestrationBrain(
                classifier=classifier,
                placement=placement,
                feedback_tracker=feedback,
                deepfield=deepfield,
            )

        return ProvisioningService(
            catalog=catalog,
            pool=OpenShiftPoolAdapter(),
            provisioner=OpenShiftProvisioningAdapter(),
            validator=OpenShiftValidationAdapter(),
            cleanup=OpenShiftCleanupAdapter(),
            db_stores=db_stores,
            placement=placement,
            workload_classifier=classifier,
            feedback_tracker=feedback,
            brain=brain,
            preflight=preflight,
            maas_key_broker=maas_key_broker,
            cluster_registry=cluster_registry,
            cluster_client_factory=cluster_client_factory,
        )
    elif mode == "rhdp":
        from app.adapters.rhdp.cleanup import RHDPCleanupAdapter
        from app.adapters.rhdp.pool import RHDPPoolAdapter
        from app.adapters.rhdp.provisioning import RHDPProvisioningAdapter
        from app.adapters.rhdp.sandbox_api import SandboxAPIClient
        from app.adapters.rhdp.validation import RHDPValidationAdapter
        sandbox_api = SandboxAPIClient()

        placement = None
        if os.environ.get("SMART_PLACEMENT_ENABLED", "true").lower() != "false":
            from app.services.placement import PlacementService
            placement = PlacementService(
                stargate_url=os.environ.get("STARGATE_API_URL", ""),
                stargate_api_key=os.environ.get("STARGATE_API_KEY", ""),
            )

        classifier = None
        if os.environ.get("WORKLOAD_PROFILING_ENABLED", "false").lower() == "true":
            from app.services.workload_classifier import WorkloadClassifier
            classifier = WorkloadClassifier()

        feedback = None
        if os.environ.get("FEEDBACK_TRACKING_ENABLED", "false").lower() == "true":
            from app.services.feedback_tracker import FeedbackTracker
            outcome_store = None
            if db_stores:
                from app.storage.stores import PostgresOutcomeStore
                outcome_store = PostgresOutcomeStore()
            feedback = FeedbackTracker(db_store=outcome_store)

        brain = None
        if os.environ.get("ORCHESTRATION_BRAIN_ENABLED", "false").lower() == "true":
            from app.services.orchestration_brain import OrchestrationBrain
            deepfield = None
            deepfield_url = os.environ.get("DEEPFIELD_API_URL", "")
            if deepfield_url:
                from app.adapters.deepfield.client import DeepFieldAdapter
                deepfield = DeepFieldAdapter(api_url=deepfield_url)
            brain = OrchestrationBrain(
                classifier=classifier,
                placement=placement,
                feedback_tracker=feedback,
                deepfield=deepfield,
            )

        return ProvisioningService(
            catalog=catalog,
            pool=RHDPPoolAdapter(sandbox_api=sandbox_api),
            provisioner=RHDPProvisioningAdapter(),
            validator=RHDPValidationAdapter(),
            cleanup=RHDPCleanupAdapter(sandbox_api=sandbox_api),
            db_stores=db_stores,
            placement=placement,
            workload_classifier=classifier,
            feedback_tracker=feedback,
            brain=brain,
        )

    classifier = None
    if os.environ.get("WORKLOAD_PROFILING_ENABLED", "false").lower() == "true":
        from app.services.workload_classifier import WorkloadClassifier
        classifier = WorkloadClassifier()

    feedback = None
    if os.environ.get("FEEDBACK_TRACKING_ENABLED", "false").lower() == "true":
        from app.services.feedback_tracker import FeedbackTracker
        outcome_store = None
        if db_stores:
            from app.storage.stores import PostgresOutcomeStore
            outcome_store = PostgresOutcomeStore()
        feedback = FeedbackTracker(db_store=outcome_store)

    placement = None
    if os.environ.get("SMART_PLACEMENT_ENABLED", "true").lower() != "false":
        from app.services.placement import PlacementService
        placement = PlacementService(
            stargate_url=os.environ.get("STARGATE_API_URL", ""),
            stargate_api_key=os.environ.get("STARGATE_API_KEY", ""),
        )

    brain = None
    if os.environ.get("ORCHESTRATION_BRAIN_ENABLED", "false").lower() == "true":
        from app.services.orchestration_brain import OrchestrationBrain
        deepfield = None
        deepfield_url = os.environ.get("DEEPFIELD_API_URL", "")
        if deepfield_url:
            from app.adapters.deepfield.client import DeepFieldAdapter
            deepfield = DeepFieldAdapter(api_url=deepfield_url)
        brain = OrchestrationBrain(
            classifier=classifier,
            placement=placement,
            feedback_tracker=feedback,
            deepfield=deepfield,
        )

    return ProvisioningService(catalog=catalog, db_stores=db_stores, workload_classifier=classifier,
                               feedback_tracker=feedback, placement=placement, brain=brain)


db_stores = _create_db_stores()
tenant_store = TenantStore(db_store=db_stores.tenants if db_stores else None)
provisioning_service = create_provisioning_service()
catalog_adapter = _create_catalog()
branding_adapter = FileBrandingAdapter()


def get_placement_service():
    return getattr(provisioning_service, "placement", None)


def get_feedback_tracker():
    return getattr(provisioning_service, "feedback_tracker", None)


def get_deepfield_adapter():
    brain = getattr(provisioning_service, "brain", None)
    if brain:
        return getattr(brain, "deepfield", None)
    return None


def get_brain():
    return getattr(provisioning_service, "brain", None)


_fleet_enrichment = None

def get_fleet_enrichment():
    global _fleet_enrichment
    if _fleet_enrichment is None:
        import os
        stargate = os.environ.get("STARGATE_API_URL", "")
        deepfield = os.environ.get("DEEPFIELD_API_URL", "")
        if stargate or deepfield:
            from app.services.fleet_enrichment import FleetEnrichment
            _fleet_enrichment = FleetEnrichment(stargate_url=stargate, deepfield_url=deepfield)
    return _fleet_enrichment
