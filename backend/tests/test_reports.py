from app.domain.reports import HandoffPackage, RepeatabilityReport, SecurityPlan


def test_repeatability_report_scores_complete_session():
    report = RepeatabilityReport(
        session_id="s-001",
        catalog_item_id="inference-overdrive-quickstart",
        version="1.0.0",
        catalog_versioned=True,
        provisioning_plan_generated=True,
        validation_passed=True,
        handoff_generated=True,
        showback_generated=True,
        cleanup_defined=True,
    )
    assert report.repeatability_score == 100


def test_repeatability_report_partial_score():
    report = RepeatabilityReport(
        session_id="s-002",
        catalog_item_id="build-a-rag-app",
        version="1.0.0",
        catalog_versioned=True,
        provisioning_plan_generated=True,
        validation_passed=False,
        handoff_generated=False,
        showback_generated=False,
        cleanup_defined=False,
    )
    assert report.repeatability_score == 40


def test_repeatability_report_zero_score():
    report = RepeatabilityReport(
        session_id="s-003",
        catalog_item_id="test",
        version="0.1.0",
    )
    assert report.repeatability_score == 0


def test_handoff_package_generated_for_ready_session():
    handoff = HandoffPackage(
        lab_title="Inference Overdrive Quick Start",
        tenant="Partner OEM A",
        catalog_item="inference-overdrive-quickstart",
        session_id="s-001",
        lab_url="https://lab.example.com/s-001",
        dashboard_url="https://dashboard.example.com/s-001",
        access_instructions="Open the lab URL and log in with your provided credentials.",
        readme="1. Open the lab URL.\n2. Run the sample workload.\n3. View the dashboard.",
    )
    assert handoff.lab_url is not None
    assert handoff.dashboard_url is not None
    md = handoff.to_markdown()
    assert "Your AI Lab is Ready" in md
    assert "Partner OEM A" in md
    assert "https://lab.example.com/s-001" in md


def test_security_plan_generated_for_lab_session():
    plan = SecurityPlan(
        namespace="lab-partner-oem-a-001",
        quota_profile="standard",
        rbac_profile="lab-user",
        network_policy_profile="restricted",
        secret_policy="no-external-secrets",
        egress_policy="deny-all-except-model-endpoint",
    )
    assert plan.namespace == "lab-partner-oem-a-001"
    artifacts = plan.planned_artifacts()
    assert "Namespace" in artifacts
    assert "ResourceQuota" in artifacts
    assert "LimitRange" in artifacts
    assert "RoleBinding" in artifacts
    assert "NetworkPolicy" in artifacts
    assert "ServiceAccount" in artifacts
