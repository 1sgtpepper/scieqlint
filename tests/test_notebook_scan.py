from __future__ import annotations

import json
from pathlib import PurePosixPath

from scieqlint.api import check_documents
from scieqlint.config.model import Config
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.notebook import NotebookScanner


def test_notebook_markdown_cells_are_scanned() -> None:
    document = _notebook(
        [
            _markdown_cell("$$\n(a+b)^2 = a^2 + b^2\n$$\n"),
        ]
    )

    result = check_documents([document], config=Config())

    assert result.math_blocks_checked == 1
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["ALG001"]
    assert result.diagnostics[0].span is not None
    assert result.diagnostics[0].span.cell == 0
    assert result.diagnostics[0].span.cell_line == 2


def test_notebook_code_cells_are_ignored() -> None:
    document = _notebook(
        [
            _code_cell("raise RuntimeError('not executed')\n"),
            _code_cell("$$\n(a+b)^2 = a^2 + b^2\n$$\n"),
        ]
    )

    result = check_documents([document], config=Config())

    assert result.math_blocks_checked == 0
    assert result.diagnostics == ()


def test_invalid_notebook_json_emits_input_diagnostic() -> None:
    document = SourceDocument.from_text(PurePosixPath("broken.ipynb"), "{", DocumentKind.NOTEBOOK)

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["INP001"]
    assert result.diagnostics[0].span is not None
    assert result.diagnostics[0].span.path == PurePosixPath("broken.ipynb")


def test_notebook_root_schema_issue_is_deterministic() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("broken.ipynb"),
        json.dumps([]),
        DocumentKind.NOTEBOOK,
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["INP002"]
    assert result.diagnostics[0].detail == "notebook root must be a JSON object"
    assert result.exit_code() == 0


def test_notebook_schema_issue_scans_readable_cells_best_effort() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("notes.ipynb"),
        json.dumps(
            {
                "cells": [_markdown_cell("$$\n(a+b)^2 = a^2 + b^2\n$$\n")],
                "metadata": {},
            }
        ),
        DocumentKind.NOTEBOOK,
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["INP002", "INP002", "ALG001"]
    assert [diagnostic.detail for diagnostic in result.diagnostics[:2]] == [
        "notebook nbformat must be an integer",
        "notebook nbformat_minor must be an integer",
    ]
    assert result.math_blocks_checked == 1


def test_notebook_schema_issue_rejects_boolean_version_fields() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("notes.ipynb"),
        json.dumps(
            {
                "cells": [],
                "metadata": {},
                "nbformat": True,
                "nbformat_minor": False,
            }
        ),
        DocumentKind.NOTEBOOK,
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.detail for diagnostic in result.diagnostics] == [
        "notebook nbformat must be an integer",
        "notebook nbformat_minor must be an integer",
    ]


def test_notebook_schema_issue_reports_missing_minor_version() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("notes.ipynb"),
        json.dumps(
            {
                "cells": [],
                "metadata": {},
                "nbformat": 4,
            }
        ),
        DocumentKind.NOTEBOOK,
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["INP002"]
    assert result.diagnostics[0].detail == "notebook nbformat_minor must be an integer"


def test_malformed_markdown_cell_source_emits_schema_warning() -> None:
    document = _notebook(
        [
            _markdown_cell(["$$\nE = m c^2\n$$\n"]),
            _markdown_cell([1]),
        ]
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["INP002"]
    assert result.diagnostics[0].span is not None
    assert result.diagnostics[0].span.cell == 1
    assert result.math_blocks_checked == 1


def test_notebook_markdown_scan_diagnostics_preserve_cell_metadata() -> None:
    document = _notebook([_markdown_cell("$$\nunterminated\n")])

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["SCAN001"]
    assert result.diagnostics[0].span is not None
    assert result.diagnostics[0].span.cell == 0
    assert result.diagnostics[0].span.cell_line == 1


def test_notebook_diagnostics_sort_by_cell_before_cell_line() -> None:
    document = _notebook(
        [
            _markdown_cell("heading\n$$\nunterminated\n"),
            _markdown_cell("$$\nunterminated\n"),
        ]
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "SCAN001",
        "SCAN001",
    ]
    assert [diagnostic.span.cell for diagnostic in result.diagnostics if diagnostic.span] == [
        0,
        1,
    ]


def test_notebook_references_preserve_cell_metadata() -> None:
    document = _notebook(
        [
            _markdown_cell("$$\nE = m c^2\n$$ {#energy}\n"),
            _markdown_cell("See {eq}`missing`.\n"),
        ]
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF002"]
    assert result.diagnostics[0].span is not None
    assert result.diagnostics[0].span.cell == 1
    assert result.diagnostics[0].span.cell_line == 1


def test_notebook_scanner_preserves_label_cell_metadata() -> None:
    document = _notebook([_markdown_cell("$$\nE = m c^2\n$$ {#energy}\n")])

    scan = NotebookScanner().scan(document, Config())

    assert len(scan.labels) == 1
    assert scan.labels[0].span.cell == 0
    assert scan.labels[0].span.cell_line == 3
    assert scan.labels[0].block_id is not None
    assert "#cell-0" in scan.labels[0].block_id


def _notebook(cells: list[dict[str, object]]) -> SourceDocument:
    text = json.dumps(
        {
            "cells": cells,
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
    )
    return SourceDocument.from_text(PurePosixPath("notes.ipynb"), text, DocumentKind.NOTEBOOK)


def _markdown_cell(source: str | list[str]) -> dict[str, object]:
    return {"cell_type": "markdown", "metadata": {}, "source": source}


def _code_cell(source: str) -> dict[str, object]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source,
    }
