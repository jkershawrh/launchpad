import importlib.util
from pathlib import Path
from subprocess import CompletedProcess

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "review_catalog_render_offline.py"


def _module():
    spec = importlib.util.spec_from_file_location("offline_render", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _candidate(
    tmp_path: Path,
    *,
    chart_path: str = "chart",
    helm_values: dict | None = None,
) -> tuple[Path, Path]:
    source = tmp_path / "source"
    chart = source / "chart"
    chart.mkdir(parents=True)
    (chart / "Chart.yaml").write_text("apiVersion: v2\nname: example\nversion: 0.1.0\n")
    intake = tmp_path / "intake.yaml"
    intake.write_text(
        yaml.safe_dump(
            {
                "catalog": {"catalog_item_id": "example-lab"},
                "sources": {
                    "workload": {
                        "revision": "a" * 40,
                        "deploy_path": chart_path,
                    }
                },
                "runtime": {
                    "deployment_type": "helm",
                    **(
                        {"workload": {"helm_values": helm_values}}
                        if helm_values is not None
                        else {}
                    ),
                },
            }
        )
    )
    return intake, source


def _runner(rendered: bytes, *, revision: str = "a" * 40, dirty: bool = False):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return CompletedProcess(args, 0, (revision + "\n").encode(), b"")
        if args[:3] == ["git", "status", "--porcelain"]:
            return CompletedProcess(args, 0, b" M values.yaml\n" if dirty else b"", b"")
        if args[:2] == ["helm", "lint"]:
            return CompletedProcess(args, 0, b"lint passed", b"")
        if args[:2] == ["helm", "template"]:
            return CompletedProcess(args, 0, rendered, b"")
        raise AssertionError(args)

    return run, calls


def _manifest(image: str) -> bytes:
    return (
        "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: example}\n"
        "spec:\n  template:\n    spec:\n      containers:\n"
        f"        - name: app\n          image: {image}\n"
    ).encode()


def test_local_render_review_is_reproducible_but_never_certifies(tmp_path: Path) -> None:
    module = _module()
    intake, source = _candidate(tmp_path)
    runner, calls = _runner(_manifest("quay.io/example/app@sha256:" + "b" * 64))

    report = module.review(intake, source, runner=runner)

    assert report["status"] == "review-ready-local"
    assert report["findings"] == []
    assert report["resource_count"] == 1
    assert report["manifest_sha256"].startswith("sha256:")
    assert report["release_eligible"] is False
    assert any(args[:2] == ["helm", "template"] for args in calls)


def test_revision_mismatch_and_dirty_source_block_before_render(tmp_path: Path) -> None:
    module = _module()
    intake, source = _candidate(tmp_path)
    mismatch_runner, mismatch_calls = _runner(b"", revision="c" * 40)
    dirty_runner, dirty_calls = _runner(b"", dirty=True)

    mismatch = module.review(intake, source, runner=mismatch_runner)
    dirty = module.review(intake, source, runner=dirty_runner)

    assert mismatch["findings"] == ["source-revision-mismatch"]
    assert dirty["findings"] == ["source-dirty"]
    assert not any(args[0] == "helm" for args in mismatch_calls + dirty_calls)


def test_path_escape_and_mutable_image_fail_closed(tmp_path: Path) -> None:
    module = _module()
    escaped_intake, source = _candidate(tmp_path, chart_path="../other")
    runner, calls = _runner(b"")
    escaped = module.review(escaped_intake, source, runner=runner)
    assert escaped["findings"] == ["chart-path-invalid"]
    assert calls == []

    valid_intake, source = _candidate(tmp_path / "valid")
    mutable_runner, _ = _runner(_manifest("quay.io/example/app:latest"))
    mutable = module.review(valid_intake, source, runner=mutable_runner)
    assert mutable["status"] == "blocked"
    assert "mutable-or-invalid-image" in mutable["findings"]


def test_renderer_failure_never_echoes_provider_output(tmp_path: Path) -> None:
    module = _module()
    intake, source = _candidate(tmp_path)
    secret = "private-renderer-output"

    def runner(args, **kwargs):
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return CompletedProcess(args, 0, ("a" * 40).encode(), b"")
        if args[:3] == ["git", "status", "--porcelain"]:
            return CompletedProcess(args, 0, b"", b"")
        return CompletedProcess(args, 1, b"", secret.encode())

    report = module.review(intake, source, runner=runner)

    assert report["findings"] == ["helm-lint-failed"]
    assert secret not in str(report)


def test_digest_image_override_is_bound_to_local_render(tmp_path: Path) -> None:
    module = _module()
    image = "quay.io/redhat-gpte/hybrid-fraud-detection@sha256:" + "a" * 64
    intake, source = _candidate(tmp_path, helm_values={"app": {"image": image}})
    runner, calls = _runner(_manifest(image))

    report = module.review(intake, source, runner=runner)

    assert report["status"] == "review-ready-local"
    assert report["image_override_applied"] is True
    assert report["helm_values_sha256"].startswith("sha256:")
    assert image not in str(report)
    template = next(args for args in calls if args[:2] == ["helm", "template"])
    assert template[-2:] == ["--set-string", "app.image=" + image]
    assert report["release_eligible"] is False


def test_secret_backed_model_override_requires_all_rendered_refs(tmp_path: Path) -> None:
    module = _module()
    image = "ghcr.io/example/app@sha256:" + "a" * 64
    intake, source = _candidate(
        tmp_path,
        helm_values={"app": {"image": image}, "model": {"endpointFromSecret": True}},
    )
    payload = yaml.safe_load(intake.read_text())
    payload["runtime"]["workload"]["runtime_secret_name"] = "model-runtime"
    intake.write_text(yaml.safe_dump(payload))
    rendered = _manifest(image) + (
        "\n---\napiVersion: v1\nkind: Pod\nmetadata: {name: refs}\n"
        "spec:\n  containers:\n  - name: refs\n    image: " + image + "\n"
        "    env:\n"
        + "".join(
            "    - name: " + key.upper().replace("-", "_") + "\n"
            "      valueFrom: {secretKeyRef: {name: model-runtime, key: " + key + "}}\n"
            for key in ("endpoint", "name", "api-key")
        )
    ).encode()
    runner, calls = _runner(rendered)

    report = module.review(intake, source, runner=runner)

    assert report["status"] == "review-ready-local"
    template = next(args for args in calls if args[:2] == ["helm", "template"])
    assert ["--set", "model.endpointFromSecret=true"] == template[-4:-2]
    assert template[-2:] == ["--set-string", "model.existingSecret=model-runtime"]
    assert "model-runtime" not in str(report)

    missing_runner, _ = _runner(_manifest(image))
    missing = module.review(intake, source, runner=missing_runner)
    assert missing["findings"] == ["model-secret-override-not-rendered"]


def test_invalid_or_extra_helm_values_fail_before_helm(tmp_path: Path) -> None:
    module = _module()
    for index, values in enumerate(
        (
            {"app": {"image": "quay.io/example/app:latest"}},
            {"app": {"image": "quay.io/example/app,other=x@sha256:" + "a" * 64}},
            {"app": {"image": "quay.io/example/app@sha256:" + "a" * 64, "secret": "x"}},
            {"model": {"endpoint": "https://private.example"}},
            {"model": {"endpointFromSecret": "true"}},
        )
    ):
        intake, source = _candidate(tmp_path / str(index), helm_values=values)
        runner, calls = _runner(b"")

        report = module.review(intake, source, runner=runner)

        assert report["findings"] == ["helm-values-unsupported-or-unsafe"]
        assert not any(args[0] == "helm" for args in calls)
        assert str(values) not in str(report)


def test_ignored_image_override_does_not_pass_render_review(tmp_path: Path) -> None:
    module = _module()
    image = "quay.io/example/intended@sha256:" + "a" * 64
    other = "quay.io/example/other@sha256:" + "b" * 64
    intake, source = _candidate(tmp_path, helm_values={"app": {"image": image}})
    runner, _ = _runner(_manifest(other))

    report = module.review(intake, source, runner=runner)

    assert report["status"] == "blocked"
    assert "image-override-not-rendered" in report["findings"]


def test_malformed_intake_fields_fail_without_echoing_values(tmp_path: Path) -> None:
    module = _module()
    intake = tmp_path / "intake.yaml"
    intake.write_text(
        yaml.safe_dump({"catalog": "private-value", "sources": "private-value", "runtime": []})
    )
    runner, calls = _runner(b"")

    report = module.review(intake, tmp_path, runner=runner)

    assert report["status"] == "blocked"
    assert report["findings"] == ["source-revision-invalid"]
    assert "private-value" not in str(report)
    assert calls == []
