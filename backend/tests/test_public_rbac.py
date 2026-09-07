from types import SimpleNamespace

from app.domain.models import LabSession
from app.services.provisioning import ProvisioningService


class FakeRbac:
    def __init__(self): self.created = []; self.deleted = []
    def create_namespaced_role_binding(self, namespace, binding): self.created.append((namespace, binding))
    def delete_namespaced_role_binding(self, name, namespace): self.deleted.append((namespace, name))


class FakeFactory:
    def __init__(self, rbac): self.rbac = rbac
    def clients(self, _cluster, *, allow_disabled=False):
        assert allow_disabled is True
        return SimpleNamespace(rbac=self.rbac)


def service_with_session(catalog_item_id="sandbox"):
    service = ProvisioningService.__new__(ProvisioningService)
    service._workshops = {}
    session = LabSession(request_id="order", tenant_id="tenant", catalog_item_id=catalog_item_id, namespace="seat-ns", cluster_ref="oberon")
    service._sessions = {session.session_id: session}
    rbac = FakeRbac()
    service.cluster_client_factory = FakeFactory(rbac)
    return service, rbac


def test_claim_binds_stable_oidc_user_to_edit_in_claimed_namespace_only():
    service, rbac = service_with_session()
    service.bind_public_participant("order", "order", "lp-stable-user")
    namespace, binding = rbac.created[0]
    assert namespace == "seat-ns"
    assert binding.role_ref.name == "edit"
    assert binding.subjects[0].name == "lp-stable-user"
    assert binding.metadata.labels["launchpad.redhat.com/order-id"] == "order"


def test_agentops_claim_also_binds_namespaced_application_log_view():
    service, rbac = service_with_session("agentops-observability")
    service.bind_public_participant("order", "order", "lp-stable-user")

    assert len(rbac.created) == 2
    assert {binding.role_ref.name for _, binding in rbac.created} == {
        "edit",
        "cluster-logging-application-view",
    }
    assert {namespace for namespace, _ in rbac.created} == {"seat-ns"}
    assert {binding.subjects[0].name for _, binding in rbac.created} == {
        "lp-stable-user"
    }


def test_agentops_removal_deletes_edit_and_log_bindings():
    service, rbac = service_with_session("agentops-observability")
    service.unbind_public_participant("order", "order", "lp-stable-user")

    assert len(rbac.deleted) == 2
    assert rbac.deleted[0][0] == "seat-ns"
    assert rbac.deleted[1][0] == "seat-ns"
    assert rbac.deleted[1][1].endswith("-logs")


def test_rotation_or_removal_deletes_only_the_participant_binding():
    service, rbac = service_with_session()
    service.unbind_public_participant("order", "order", "lp-stable-user")
    assert rbac.deleted[0][0] == "seat-ns"
    assert rbac.deleted[0][1].startswith("launchpad-participant-")
