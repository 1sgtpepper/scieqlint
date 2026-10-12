from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")


def _job_block(name: str) -> str:
    marker = f"  {name}:\n"
    start = WORKFLOW.index(marker)
    match = re.search(r"\n  [a-z][a-z0-9-]*:\n", WORKFLOW[start + len(marker) :])
    if match is None:
        return WORKFLOW[start:]
    return WORKFLOW[start : start + len(marker) + match.start()]


def test_coverage_runs_only_on_the_minimum_supported_python() -> None:
    matrix = _job_block("test-matrix")

    assert 'python-version: ["3.11", "3.12", "3.13"]' in matrix
    assert "if: matrix.python-version != '3.11'\n        run: pytest" in matrix
    assert "if: matrix.python-version == '3.11'\n        run: pytest --cov=scieqlint" in matrix
    assert matrix.count("pytest --cov=scieqlint") == 1
    assert (
        "if: matrix.python-version == '3.11'\n        run: |\n          coverage report"
    ) in matrix
    assert "if: matrix.python-version == '3.11'\n        uses: codecov/codecov-action" in matrix
