from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "content-intel-xeon6-agent-201/modules/ROOT/pages/02-deploy-tools.adoc"


def test_terminal_mcp_exercises_use_namespace_service_without_route_tls() -> None:
    content = PAGE.read_text()

    assert content.count('MCP_URL="http://solution-tools:8095"') == 5
    assert "oc get route tools" not in content
    assert "curl -k" not in content
    assert "curl --insecure" not in content
    assert "keeps the exercise inside your assigned namespace" in content
