from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_remote_agent_drivers_bind_to_the_labeled_execution_cluster():
    seat = (ROOT / "scripts/certify-agent-201-remote-seat.sh").read_text()
    journey = (ROOT / "scripts/certify-agent-201-remote-journey.sh").read_text()

    for script in (seat, journey):
        assert "launchpad\\.redhat\\.com/cluster-id" in script
        assert 'actual_cluster" != "$expected_cluster' in script
        assert "LAUNCHPAD_INGRESS_IP" in script
        assert "ARENA_INGRESS_IP" not in script


def test_remote_agent_drivers_exercise_the_participant_boundary_and_tools():
    seat = (ROOT / "scripts/certify-agent-201-remote-seat.sh").read_text()
    journey = (ROOT / "scripts/certify-agent-201-remote-journey.sh").read_text()

    assert "deploy/showroom -c terminal" in seat
    assert "litellm-api-key" in seat
    assert '--from-literal=api-key="$MAAS_API_KEY"' in seat
    assert 'api_key="$(printf' not in seat
    assert "ADVISOR_MODEL" in seat
    assert 'select(.error != null)' in journey
    assert "intel_hardware_lookup" in journey
    assert "openshift_capabilities" in journey
    assert "reference_architectures" in journey


def test_catalog_agent_driver_limits_probe_exec_access_to_the_seat_namespace():
    driver = (ROOT / "scripts/certify-agent-201-catalog-seat.sh").read_text()

    assert "launchpad-certification-probe" in driver
    assert "--clusterrole=edit" in driver
    assert "--serviceaccount=partner-ai-launchpad:launchpad-provisioner" in driver
    assert 'delete rolebinding "$probe_binding"' in driver
    assert '--namespace "$namespace"' in driver
