from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path


def _workflow_job(workflow: str, name: str) -> str:
    marker = f"  {name}:\n"
    start = workflow.index(marker)
    match = re.search(r"\n  [a-z][a-z0-9-]*:\n", workflow[start + len(marker) :])
    if match is None:
        return workflow[start:]
    return workflow[start : start + len(marker) + match.start()]


def test_release_version_metadata_is_consistent() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    init_tree = ast.parse(Path("src/scieqlint/__init__.py").read_text(encoding="utf-8"))
    citation = Path("CITATION.cff").read_text(encoding="utf-8")

    assert project["version"] == "1.1.0"
    assert _assigned_string(init_tree, "__version__") == project["version"]
    assert f"version: {project['version']}" in citation


def test_implementation_status_uses_the_current_release_version() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]

    for path in (
        Path("IMPLEMENTATION_STATUS.md"),
        Path("PACK_MANIFEST.md"),
        Path("SPEC.md"),
    ):
        text = path.read_text(encoding="utf-8")
        assert f"v{project['version']}" in text, path
        assert "v0.1.5 analyzer" not in text, path


def test_current_release_remains_pre_alpha() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert "Development Status :: 2 - Pre-Alpha" in project["classifiers"]
    assert not any("Production/Stable" in classifier for classifier in project["classifiers"])


def test_documentation_url_points_to_current_repository_docs() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["urls"]["Documentation"] == (
        "https://github.com/1sgtpepper/scieqlint/tree/main/docs"
    )


def test_release_workflow_uses_tag_gated_trusted_publishing() -> None:
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "if: startsWith(github.ref, 'refs/tags/v')" in workflow
    assert "environment: pypi" in workflow
    assert "id-token: write" in workflow
    assert re.search(
        r"uses: pypa/gh-action-pypi-publish@[0-9a-f]{40}",
        workflow,
    )
    assert "username:" not in workflow
    assert "password:" not in workflow


def test_release_workflow_enforces_version_and_behavioral_evidence() -> None:
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    assert 'version("scieqlint")' in workflow
    assert "${GITHUB_REF_NAME#v}" in workflow
    assert "sdist_version" in workflow
    assert 'test "$sdist_version" = "$source_version"' in workflow
    assert "tests/test_accuracy_benchmarks.py" in workflow
    assert "tests/test_stabilization.py" in workflow
    smoke_start = workflow.index("\n  smoke:")
    publish_start = workflow.index("\n  publish:")
    assert (
        smoke_start
        < workflow.index("Verify source, wheel, source distribution, and tag versions")
        < publish_start
    )
    release_gate_start = workflow.index("Enforce stable-release accuracy")
    assert smoke_start < release_gate_start < publish_start
    release_gate = workflow[release_gate_start:publish_start]
    assert "/tmp/scieqlint-release-wheel-smoke/bin/python -m pip install pytest" in release_gate
    assert "/tmp/scieqlint-release-sdist-smoke/bin/python -m pip install pytest" in release_gate
    assert "SCIEQLINT_RELEASE_GATE=1 python -m pytest" not in release_gate
    assert "/tmp/scieqlint-release-wheel-smoke/bin/python -m pytest" in release_gate
    assert "/tmp/scieqlint-release-sdist-smoke/bin/python -m pytest" in release_gate
    assert release_gate.count("SCIEQLINT_RELEASE_GATE=1") == 2
    assert "-o pythonpath=" in release_gate
    assert "pip install -e" not in release_gate
    assert "PYTHONPATH=" not in release_gate
    assert re.search(
        r"(?m)^  publish:\n"
        r"    needs: smoke$",
        workflow,
    )


def test_release_workflow_publishes_the_exact_smoke_verified_artifact() -> None:
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    build = _workflow_job(workflow, "build")
    smoke = _workflow_job(workflow, "smoke")
    publish = _workflow_job(workflow, "publish")

    assert workflow.count("uses: actions/upload-artifact@") == 1
    assert "id: release-artifact" in build
    assert "distribution_id: ${{ steps.release-artifact.outputs.artifact-id }}" in build
    assert "distribution_digest" not in build
    assert "if-no-files-found: error" in build

    assert "needs: build" in smoke
    assert "distribution_id: ${{ needs.build.outputs.distribution_id }}" in smoke
    assert "artifact-ids: ${{ needs.build.outputs.distribution_id }}" in smoke
    assert "Approve verified release artifact" not in smoke
    assert "digest-mismatch" not in smoke
    assert "name: dist" not in smoke
    assert "/tmp/scieqlint-release-wheel-smoke/bin/python -m pip install dist/*.whl" in smoke
    assert "/tmp/scieqlint-release-sdist-smoke/bin/python -m pip install dist/*.tar.gz" in smoke
    assert "mechanics preset missing from installed sdist" in smoke

    assert "needs: smoke" in publish
    assert "artifact-ids: ${{ needs.smoke.outputs.distribution_id }}" in publish
    assert "distribution_digest" not in publish
    assert "digest-mismatch" not in publish
    assert "name: dist" not in publish
    assert "actions/checkout@" not in publish
    assert "python -m build" not in publish


def test_ci_test_matrix_covers_declared_python_versions() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    declared_versions = sorted(
        classifier.rsplit(" :: ", 1)[1]
        for classifier in project["classifiers"]
        if classifier.startswith("Programming Language :: Python :: 3.")
    )

    matrix_line = next(
        line.strip()
        for line in workflow.splitlines()
        if line.strip().startswith("python-version: [")
    )

    assert declared_versions == ["3.11", "3.12", "3.13"]
    for version in declared_versions:
        assert f'"{version}"' in matrix_line
    assert "python-version: ${{ matrix.python-version }}" in workflow
    assert "if: matrix.python-version == '3.11'" in workflow
    assert re.search(
        r"(?m)^  test:\n    name: test\n    runs-on: ubuntu-latest\n"
        r"    needs: \[public-regression-replay, test-matrix\]",
        workflow,
    )


def _assigned_string(tree: ast.Module, name: str) -> str:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    value = node.value
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        return value.value
    raise AssertionError(f"missing string assignment: {name}")
