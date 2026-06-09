from __future__ import annotations

from pathlib import PurePosixPath

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
