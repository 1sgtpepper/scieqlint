from __future__ import annotations

from pathlib import Path


def test_pr_template_is_concise_and_complete() -> None:
    template = Path(".github/PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")

    assert [line for line in template.splitlines() if line.startswith("## ")] == [
        "## Summary",
        "## Linked issue",
        "## Test",
    ]
    for verbose_section in [
        "## PR Checklist",
        "## Release target",
        "## Single layer changed",
        "## Behavior impact",
        "## Dependency checklist",
        "## Local checks",
    ]:
        assert verbose_section not in template


def test_issue_templates_require_reproduction_only_for_bugs() -> None:
    bug = Path(".github/ISSUE_TEMPLATE/0_bug.yml").read_text(encoding="utf-8")
    feature = Path(".github/ISSUE_TEMPLATE/1_feature.md").read_text(encoding="utf-8")
    task = Path(".github/ISSUE_TEMPLATE/2_task.md").read_text(encoding="utf-8")
    docs = Path(".github/ISSUE_TEMPLATE/3_documentation.md").read_text(encoding="utf-8")

    assert "id: reproduction" in bug
    assert "  - bug" in bug
    assert "needs reproduction" not in bug
    assert _field_required(bug, "reproduction")
    assert _field_required(bug, "expected-behavior")
    assert _field_required(bug, "affected-version")
    for template in [feature, task, docs]:
        assert "## Problem" in template
        assert "## Expected behavior" in template
        assert "Reproduction" not in template
        assert "## In scope" not in template


def test_pr_dependency_guide_is_in_docs_nav() -> None:
    nav = Path("mkdocs.yml").read_text(encoding="utf-8")
    guide = Path("docs/contributing/pr-dependency-checks.md").read_text(encoding="utf-8")

    assert "PR dependency checks: contributing/pr-dependency-checks.md" in nav
    for phrase in [
        "Dependency map",
        "Changelog rule",
        "Negative checks",
        "Diagnostic code, severity, or message",
        "Text, JSON, GitHub, or SARIF output",
        "PACK_MANIFEST.md",
    ]:
        assert phrase in guide


def test_contributing_docs_nav_is_reflected_in_spec() -> None:
    nav = Path("mkdocs.yml").read_text(encoding="utf-8")
    spec = Path("SPEC.md").read_text(encoding="utf-8")

    contributing_pages = [
        line.split(": ", 1)[1].strip()
        for line in nav.splitlines()
        if line.startswith("      - ") and ": contributing/" in line
    ]

    for page in contributing_pages:
        assert f"docs/{page}" in spec


def _field_required(template: str, field_id: str) -> bool:
    field = template.split(f"id: {field_id}", 1)[1]
    next_field = field.find("\n  - type:")
    if next_field != -1:
        field = field[:next_field]
    return "validations:\n      required: true" in field
