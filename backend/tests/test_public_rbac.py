from types import SimpleNamespace

from app.domain.models import LabSession
from app.services.provisioning import ProvisioningService


class FakeRbac:
    def __init__(self): self.created = []; self.deleted = []
    def create_namespaced_role_binding(self, namespace, binding): self.created.append((namespace, binding))
    def delete_namespaced_role_binding(self, name, namespace): self.deleted.append((namespace, name))


class FakeFactory:
    def __init__(self, rbac): self.rbac = rbac
    def clients(self, _cluster): return SimpleNamespace(rbac=self.rbac)


def service_with_session():
    service = ProvisioningService.__new__(ProvisioningService)
    service._workshops = {}
    session = LabSession(request_id="order", tenant_id="tenant", catalog_item_id="sandbox", namespace="seat-ns", cluster_ref="oberon")
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


def test_rotation_or_removal_deletes_only_the_participant_binding():
    service, rbac = service_with_session()
    service.unbind_public_participant("order", "order", "lp-stable-user")
    assert rbac.deleted[0][0] == "seat-ns"
    assert rbac.deleted[0][1].startswith("launchpad-participant-")
