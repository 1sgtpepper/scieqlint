from __future__ import annotations

from pathlib import Path


def test_pr_template_links_dependency_checklist() -> None:
    template = Path(".github/PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")

    assert "## Dependency checklist" in template
    assert "docs/contributing/pr-dependency-checks.md" in template
    assert "<!--" not in _dependency_section(template)
    assert (
        "I checked `docs/contributing/pr-dependency-checks.md` and updated every dependent artifact"
        in template
    )
    assert "intentionally skipped" not in template
    assert "| Change area |" not in template


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


def _dependency_section(template: str) -> str:
    start = template.index("## Dependency checklist")
    end = template.index("## Local checks")
    return template[start:end]
