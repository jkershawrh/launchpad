from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_scaffold_cli_turns_quickstart_repo_into_reviewable_draft(tmp_path: Path):
    source = tmp_path / "source"
    pages = source / "showroom/modules/ROOT/pages"
    pages.mkdir(parents=True)
    (source / "site.yml").write_text(
        "content:\n  sources:\n    - url: .\n      start_path: showroom\n"
    )
    (source / "showroom/antora.yml").write_text(
        "name: example\ntitle: Example\nversion: ~\nnav:\n  - modules/ROOT/nav.adoc\n"
    )
    (source / "showroom/modules/ROOT/nav.adoc").write_text(
        "* xref:index.adoc[Start]\n"
    )
    (pages / "index.adoc").write_text("= Start\n")
    chart = source / "deploy/chart"
    chart.mkdir(parents=True)
    (chart / "Chart.yaml").write_text(
        "apiVersion: v2\nname: example\nversion: 0.1.0\n"
    )
    (chart / "values.yaml").write_text("{}\n")
    templates = chart / "templates"
    templates.mkdir()
    (templates / "deployment.yaml").write_text(
        """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: example
spec:
  template:
    spec:
      containers:
        - name: app
          image: quay.io/example/app:latest
""".lstrip()
    )
    subprocess.run(["git", "init", "--quiet"], cwd=source, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Launchpad Test", "-c", "user.email=test@example.com", "add", "."],
        cwd=source,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Launchpad Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--quiet",
            "-m",
            "fixture",
        ],
        cwd=source,
        check=True,
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    intake_path = tmp_path / "intake.yaml"
    report_path = tmp_path / "report.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/catalog_onboarding.py",
            "scaffold",
            "--repo-url",
            "https://github.com/example/quickstart.git",
            "--revision",
            revision,
            "--catalog-id",
            "example-quickstart",
            "--display-name",
            "Example Quickstart",
            "--source-dir",
            str(source),
            "--output",
            str(intake_path),
            "--report",
            str(report_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    intake = yaml.safe_load(intake_path.read_text())
    report = json.loads(report_path.read_text())
    assert intake["catalog"]["status"] == "draft"
    assert intake["runtime"]["allowed_exposure_policies"] == ["internal"]
    assert intake["certification"]["max_workshop_seats"] == 1
    assert intake["certification"]["activation_blockers"]
    assert report["discovery_status"] == "pass"
    assert report["workload"]["deployment_type"] == "helm"
    assert report["inventory"] == intake["discovery"]["inventory"]
    assert report["inventory"]["images"] == [
        {
            "path": "deploy/chart/templates/deployment.yaml",
            "reference": "quay.io/example/app:latest",
            "source": "manifest",
        }
    ]
    assert report["inventory"]["mutable_images"] == [
        {
            "path": "deploy/chart/templates/deployment.yaml",
            "reference": "quay.io/example/app:latest",
            "source": "manifest",
        }
    ]

    first_catalog = tmp_path / "catalog-first.yaml"
    second_catalog = tmp_path / "catalog-second.yaml"
    for output in (first_catalog, second_catalog):
        draft_result = subprocess.run(
            [
                sys.executable,
                "scripts/catalog_onboarding.py",
                "draft",
                str(report_path),
                "--output",
                str(output),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert draft_result.returncode == 0, draft_result.stderr
    assert first_catalog.read_bytes() == second_catalog.read_bytes()
    catalog = yaml.safe_load(first_catalog.read_text())
    assert catalog["status"] == "draft"
    assert catalog["metadata"]["allowed_exposure_policies"] == ["internal"]
    assert catalog["metadata"]["max_workshop_seats"] == 1
    assert catalog["metadata"]["activation_blockers"]


def test_draft_cli_fails_closed_without_writing_unsafe_receipt(tmp_path: Path):
    receipt_path = tmp_path / "unsafe-receipt.json"
    output_path = tmp_path / "catalog.yaml"
    receipt_path.write_text(
        json.dumps(
            {
                "schema": "launchpad.redhat.com/catalog-discovery-receipt/v1",
                "discovery_status": "fail",
                "errors": ["source discovery failed"],
                "draft_intake": {},
            }
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/catalog_onboarding.py",
            "draft",
            str(receipt_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "successful repository discovery" in result.stderr
    assert not output_path.exists()


def test_scaffold_cli_rejects_local_checkout_at_another_revision(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=source, check=True)
    (source / "README.md").write_text("# Example\n")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Launchpad Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--quiet",
            "-m",
            "fixture",
        ],
        cwd=source,
        check=True,
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/catalog_onboarding.py",
            "scaffold",
            "--repo-url",
            "https://github.com/example/quickstart.git",
            "--revision",
            "d" * 40,
            "--catalog-id",
            "example-quickstart",
            "--display-name",
            "Example Quickstart",
            "--source-dir",
            str(source),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "does not match requested immutable revision" in result.stderr
