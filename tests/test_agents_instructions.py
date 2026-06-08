from __future__ import annotations

from pathlib import Path


def test_agents_instructions_point_to_repo_contracts() -> None:
    instructions = Path("AGENTS.md").read_text(encoding="utf-8")

    for required in [
        "CONTRIBUTING.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
        "docs/contributing/pr-dependency-checks.md",
        "docs/contributing/review-guide.md",
        "docs/contributing/testing.md",
        ".github/ISSUE_TEMPLATE/",
        "SECURITY.md",
    ]:
        assert required in instructions

    assert "read `CONTRIBUTING.md` in full" in instructions
    assert "update every dependent artifact" in instructions
