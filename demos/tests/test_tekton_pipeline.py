#!/usr/bin/env python3
"""Tests for Tekton pipeline manifests."""
import pytest
import yaml
from pathlib import Path


@pytest.fixture
def pipeline_dir(project_root):
    return project_root / "deploy" / "pipelines"


class TestTektonPipeline:
    def test_pipeline_yaml_exists(self, pipeline_dir):
        assert (pipeline_dir / "pipeline.yaml").exists()

    def test_pipeline_yaml_parses(self, pipeline_dir):
        content = yaml.safe_load((pipeline_dir / "pipeline.yaml").read_text())
        assert content is not None
        assert content["kind"] == "Pipeline"

    def test_pipeline_has_tasks(self, pipeline_dir):
        content = yaml.safe_load((pipeline_dir / "pipeline.yaml").read_text())
        tasks = content["spec"]["tasks"]
        task_names = [t["name"] for t in tasks]
        assert "clone" in task_names
        assert "build-gateway" in task_names
        assert "build-frontend" in task_names
        assert "deploy" in task_names

    def test_pipeline_has_workspace(self, pipeline_dir):
        content = yaml.safe_load((pipeline_dir / "pipeline.yaml").read_text())
        workspaces = content["spec"]["workspaces"]
        assert any(w["name"] == "source" for w in workspaces)

    def test_pipeline_has_params(self, pipeline_dir):
        content = yaml.safe_load((pipeline_dir / "pipeline.yaml").read_text())
        params = content["spec"]["params"]
        param_names = [p["name"] for p in params]
        assert "git-url" in param_names
        assert "image-registry" in param_names

    def test_build_tasks_reference_containerfiles(self, pipeline_dir):
        text = (pipeline_dir / "pipeline.yaml").read_text()
        assert "gateway/Containerfile" in text
        assert "frontend/Containerfile" in text

    def test_deploy_task_has_rollout(self, pipeline_dir):
        text = (pipeline_dir / "pipeline.yaml").read_text()
        assert "oc rollout restart" in text


class TestTektonPipelineRun:
    def test_pipelinerun_yaml_exists(self, pipeline_dir):
        assert (pipeline_dir / "pipelinerun.yaml").exists()

    def test_pipelinerun_references_pipeline(self, pipeline_dir):
        content = yaml.safe_load((pipeline_dir / "pipelinerun.yaml").read_text())
        assert content["spec"]["pipelineRef"]["name"] == "intel-rh-demo-build"

    def test_pipelinerun_has_workspace(self, pipeline_dir):
        content = yaml.safe_load((pipeline_dir / "pipelinerun.yaml").read_text())
        workspaces = content["spec"]["workspaces"]
        assert len(workspaces) > 0
