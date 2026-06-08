from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path


def test_release_version_metadata_is_consistent() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    init_tree = ast.parse(Path("src/scieqlint/__init__.py").read_text(encoding="utf-8"))
    citation = Path("CITATION.cff").read_text(encoding="utf-8")

    assert project["version"] == "0.1.5"
    assert _assigned_string(init_tree, "__version__") == project["version"]
    assert f"version: {project['version']}" in citation


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


def _assigned_string(tree: ast.Module, name: str) -> str:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    value = node.value
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        return value.value
    raise AssertionError(f"missing string assignment: {name}")
