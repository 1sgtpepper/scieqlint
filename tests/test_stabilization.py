from __future__ import annotations

import os
from pathlib import PurePosixPath
from time import perf_counter

import pytest

from scieqlint.api import check_documents
from scieqlint.config.model import Config
from scieqlint.io.source import DocumentKind, SourceDocument


def test_representative_project_run_keeps_linear_result_counts() -> None:
    documents = tuple(
        SourceDocument.from_text(
            PurePosixPath(f"chapter-{index:03}.md"),
            "\n".join(["$$", "E = m c^2", "$$", "See {eq}`missing`."]),
            DocumentKind.MARKDOWN,
        )
        for index in range(120)
    )

    result = check_documents(documents, config=Config())

    assert result.files_checked == 120
    assert result.math_blocks_checked == 120
    assert len(result.diagnostics) == 120
    assert {diagnostic.code for diagnostic in result.diagnostics} == {"REF002"}


@pytest.mark.skipif(
    os.environ.get("SCIEQLINT_RELEASE_GATE") != "1",
    reason="stable-release performance is enforced by the release workflow",
)
def test_stable_release_representative_workload_meets_the_time_budget() -> None:
    body = "\n".join(
        [
            *(line for index in range(5) for line in ("$$", f"x_{index}=x_{index}", "$$")),
            *(f"See {{eq}}`missing-{index}`." for index in range(5)),
        ]
    )
    documents = tuple(
        SourceDocument.from_text(
            PurePosixPath(f"chapter-{index:03}.md"),
            body,
            DocumentKind.MARKDOWN,
        )
        for index in range(100)
    )

    started = perf_counter()
    result = check_documents(documents, config=Config())
    elapsed = perf_counter() - started

    assert result.files_checked == 100
    assert result.math_blocks_checked == 500
    assert len(result.diagnostics) == 500, "expected 500 missing-reference diagnostics"
    assert {diagnostic.code for diagnostic in result.diagnostics} == {"REF002"}
    assert elapsed < 3.0, f"representative release workload took {elapsed:.3f}s (budget: 3.0s)"
