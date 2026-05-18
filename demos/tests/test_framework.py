"""
Test Framework for Intel-Red Hat Partner AI Demo Platform

This module provides the base test infrastructure for validating
all artifacts using TDD methodology with stage gates.
"""

import pytest
import yaml
import json
from pathlib import Path
from typing import Dict, List, Any


class ValidationMatrix:
    """Loads and validates test matrices for stage gates"""

    def __init__(self, matrix_file: Path):
        self.matrix_file = matrix_file
        self.matrix = self._load_matrix()

    def _load_matrix(self) -> Dict:
        """Load validation matrix from YAML"""
        if not self.matrix_file.exists():
            return {}

        with open(self.matrix_file, 'r') as f:
            return yaml.safe_load(f) or {}

    def get_stage_matrix(self, stage: str) -> Dict:
        """Get validation matrix for specific stage"""
        return self.matrix.get(stage, {})

    def validate_stage_criteria(self, stage: str, results: Dict) -> tuple[bool, float]:
        """
        Validate stage results against matrix criteria

        Returns:
            tuple: (passed, score_percentage)
        """
        stage_matrix = self.get_stage_matrix(stage)
        if not stage_matrix:
            return False, 0.0

        total_points = 0
        earned_points = 0

        for category, checks in stage_matrix.items():
            for check_name, criteria in checks.items():
                total_points += criteria.get('points', 1)
                if results.get(f"{category}.{check_name}") == "PASS":
                    earned_points += criteria.get('points', 1)

        if total_points == 0:
            return False, 0.0

        score_pct = (earned_points / total_points) * 100
        passed = score_pct >= 90.0  # 90% threshold

        return passed, score_pct


class RubricValidator:
    """Validates artifacts against defined rubrics"""

    def __init__(self, rubric_dir: Path):
        self.rubric_dir = rubric_dir
        self.rubrics = self._load_rubrics()

    def _load_rubrics(self) -> Dict:
        """Load all rubric files"""
        rubrics = {}
        if not self.rubric_dir.exists():
            return rubrics

        for rubric_file in self.rubric_dir.glob("*.yaml"):
            with open(rubric_file, 'r') as f:
                rubric_data = yaml.safe_load(f)
                rubrics[rubric_file.stem] = rubric_data

        return rubrics

    def get_rubric(self, artifact_type: str) -> Dict:
        """Get rubric for specific artifact type"""
        return self.rubrics.get(artifact_type, {})

    def score_artifact(self, artifact_type: str, checks: Dict[str, bool]) -> float:
        """
        Score an artifact against its rubric

        Args:
            artifact_type: Type of artifact (container, manifest, etc.)
            checks: Dict of check_name -> pass/fail

        Returns:
            score as percentage (0-100)
        """
        rubric = self.get_rubric(artifact_type)
        if not rubric:
            return 0.0

        criteria = rubric.get('criteria', {})
        total_points = sum(c.get('points', 1) for c in criteria.values())

        if total_points == 0:
            return 0.0

        earned_points = sum(
            criteria[check_name].get('points', 1)
            for check_name, passed in checks.items()
            if passed and check_name in criteria
        )

        return (earned_points / total_points) * 100


# Pytest fixtures for testing framework

@pytest.fixture
def validation_matrix(project_root) -> ValidationMatrix:
    """Load validation matrix"""
    matrix_file = project_root / "tests" / "validation_matrix.yaml"
    return ValidationMatrix(matrix_file)


@pytest.fixture
def rubric_validator(project_root) -> RubricValidator:
    """Load rubric validator"""
    rubric_dir = project_root / "tests" / "rubrics"
    return RubricValidator(rubric_dir)


# Sample test to ensure framework is working

def test_framework_loads():
    """Test that the test framework itself loads successfully"""
    assert ValidationMatrix is not None
    assert RubricValidator is not None


def test_validation_matrix_initializes(project_root):
    """Test validation matrix can be initialized"""
    matrix_file = project_root / "tests" / "validation_matrix.yaml"
    validator = ValidationMatrix(matrix_file)
    assert validator is not None


def test_rubric_validator_initializes(project_root):
    """Test rubric validator can be initialized"""
    rubric_dir = project_root / "tests" / "rubrics"
    validator = RubricValidator(rubric_dir)
    assert validator is not None


def test_no_duplicate_project_root(project_root):
    """project_root fixture should only be defined in conftest.py"""
    import re
    tests_dir = project_root / "tests"
    pattern = re.compile(r'def project_root\(')
    duplicates = []
    for test_file in tests_dir.glob("test_*.py"):
        content = test_file.read_text()
        if pattern.search(content):
            duplicates.append(test_file.name)
    assert len(duplicates) == 0, \
        f"project_root fixture duplicated in: {duplicates}"


def test_no_continue_on_error_in_ci(project_root):
    """CI pipeline should not use continue-on-error"""
    ci_file = project_root / ".github" / "workflows" / "ci.yaml"
    if not ci_file.exists():
        pytest.skip("CI file not found")
    content = ci_file.read_text()
    assert 'continue-on-error: true' not in content, \
        "CI should not use continue-on-error: true"


def test_no_makefile_dash_prefix_tests(project_root):
    """Makefile should not use - prefix on test commands"""
    makefile = project_root / "Makefile"
    if not makefile.exists():
        pytest.skip("Makefile not found")
    content = makefile.read_text()
    import re
    dash_pytest = re.findall(r'^\t-\$\(PYTEST\)', content, re.MULTILINE)
    assert len(dash_pytest) == 0, \
        f"Makefile has {len(dash_pytest)} test commands with - prefix"
