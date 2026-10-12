from __future__ import annotations

from pathlib import Path


def test_agent_instruction_files_point_to_repo_contracts() -> None:
    agents_path = Path("AGENTS.md")
    agents = agents_path.read_text(encoding="utf-8")
    _assert_repo_contracts(agents)

    instructions_path = Path("CLAUDE.md")
    instructions = instructions_path.read_text(encoding="utf-8")
    assert "[`AGENTS.md`](AGENTS.md)" in instructions
    assert (instructions_path.parent / "AGENTS.md").read_text(encoding="utf-8") == agents


def _assert_repo_contracts(instructions: str) -> None:
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
