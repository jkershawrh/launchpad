from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]


def _runner_module():
    spec = importlib.util.spec_from_file_location(
        "catalog_certification_cluster_rbac_runner",
        ROOT / "scripts/catalog_certification.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cleanup_observation_counts_cluster_role_binding_subjects(monkeypatch):
    runner = _runner_module()
    payload = {
        "items": [
            {
                "subjects": [
                    {"kind": "ServiceAccount", "namespace": "seat-a", "name": "pipeline"},
                    {"kind": "ServiceAccount", "namespace": "unrelated", "name": "pipeline"},
                ]
            }
        ]
    }

    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout=json.dumps(payload), stderr=""
        ),
    )

    counts = runner._resource_counts(
        ["clusterrolebinding-subjects.rbac.authorization.k8s.io"],
        workshop_id="workshop-1",
        kubeconfig="flightpath-kubeconfig",
        namespaces=["seat-a"],
    )

    assert counts == {
        "clusterrolebinding-subjects.rbac.authorization.k8s.io": 1
    }
