from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_showroom_shell_branding_is_reproducible_and_excludes_demo_platform():
    builder = (ROOT / "scripts/build_branded_showroom_ui.py").read_text()
    workflow = (ROOT / ".github/workflows/showroom-ui-release.yml").read_text()

    assert 'alt=\\"Red Hat\\"' in builder
    assert 'alt=\\"Intel\\"' in builder
    assert "Demo Platform branding remains" in builder
    assert "UPSTREAM_COMMIT: 19cf40e863bd98e226f843d2d5c11c05f4cd3cd6" in workflow
    assert "npm run test:run" in workflow
    assert "sha256sum" in workflow
