from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import PurePosixPath

import pytest

from scieqlint.api import check_documents
from scieqlint.config.model import ChecksConfig, Config, SymbolsConfig
from scieqlint.diag.model import Severity, SourceSpan
from scieqlint.io.limits import DEFAULT_MAX_FILE_BYTES
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.report.github import GitHubReporter
from scieqlint.report.json import JsonReporter
from scieqlint.report.sarif import SarifReporter
from scieqlint.report.text import TextReporter
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


@pytest.mark.public_regression
def test_notebook_diagnostic_cell_line_uses_markdown_splitline_boundaries() -> None:
    document = _notebook([_markdown_cell("Heading\u2028See {eq}`missing`.\n")])

    result = check_documents([document], config=Config())

    start = document.text.index("missing")
    end = start + len("missing")
    [diagnostic] = result.diagnostics
    assert (
        diagnostic.code,
        diagnostic.severity,
        diagnostic.message,
        diagnostic.equation,
        diagnostic.detail,
        diagnostic.hint,
        diagnostic.rule,
        diagnostic.suppressed,
        diagnostic.suppression_reason,
        diagnostic.profile,
        diagnostic.provenance_ids,
        diagnostic.properties,
    ) == (
        "REF002",
        Severity.WARNING,
        "equation reference target not found: missing",
        None,
        "reference text: {eq}`missing`",
        None,
        "references",
        False,
        None,
        None,
        (),
        (),
    )
    span = diagnostic.span
    assert span is not None
    assert (
        span.path,
        span.start,
        span.end,
        span.line,
        span.col,
        span.end_line,
        span.end_col,
        span.cell,
        span.cell_line,
    ) == (
        document.path,
        start,
        end,
        1,
        start + 1,
        1,
        end,
        0,
        2,
    )
    assert _raw_segments(document, span) == list("missing")
    assert result.files_checked == 1
    assert result.math_blocks_checked == 0
    assert result.exit_code() == 0


def test_notebook_scanner_spans_slice_the_original_json_source() -> None:
    document = _notebook(
        [
            _markdown_cell(
                "<!-- scieqlint-symbol: unique = variable -->\n"
                "$$\n"
                "z = z\n"
                "$$ {#unique-equation}\n\n"
                "See {eq}`unique-equation`.\n"
            )
        ]
    )

    scan = NotebookScanner().scan(document, Config())

    spans = (
        scan.blocks[0].span,
        scan.labels[0].span,
        scan.references[0].span,
        scan.symbol_directives[0].span,
    )

    def source_slice(span: SourceSpan | None) -> str:
        assert span is not None
        assert span.path == document.path
        assert span.cell == 0
        assert span.cell_line is not None
        return document.text[span.start : span.end]

    assert source_slice(spans[0]) == "z = z"
    assert "unique-equation" in source_slice(spans[1])
    assert source_slice(spans[2]) == "unique-equation"
    assert source_slice(spans[3]) == "unique"


@pytest.mark.parametrize(
    ("ranges", "message"),
    [
        ((), "requires at least one raw range"),
        (((-1, 1),), "must be ordered and non-empty"),
        (((0, 0),), "must be ordered and non-empty"),
        (((1, 3), (2, 4)), "must be ordered and non-empty"),
    ],
)
def test_source_segment_rejects_invalid_raw_range_contracts(
    ranges: tuple[tuple[int, int], ...],
    message: str,
) -> None:
    from scieqlint.diag.model import SourceSegment

    with pytest.raises(ValueError, match=message):
        SourceSegment(
            ranges=ranges,
            line=1,
            col=1,
            end_line=1,
            end_col=1,
        )


@pytest.mark.parametrize(
    ("source_ranges", "start", "end", "message"),
    [
        ((((0, 1),),), -1, 0, "outside its source"),
        ((((0, 1),),), 1, 0, "outside its source"),
        ((((0, 1),),), 0, 2, "outside its source"),
        (((),), 0, 1, "has no raw range"),
    ],
)
def test_notebook_span_mapping_rejects_invalid_logical_source_contracts(
    source_ranges: tuple[tuple[tuple[int, int], ...], ...],
    start: int,
    end: int,
    message: str,
) -> None:
    from scieqlint.scan.notebook_input import (
        NotebookSourceLocationError,
        map_notebook_span,
    )

    document = SourceDocument.from_text(
        PurePosixPath("mapping.ipynb"),
        "x",
        DocumentKind.NOTEBOOK,
    )
    logical_span = SourceSpan(
        path=PurePosixPath("mapping.md"),
        start=start,
        end=end,
        line=1,
        col=1,
        end_line=1,
        end_col=1,
    )

    with pytest.raises(NotebookSourceLocationError, match=message):
        map_notebook_span(
            document,
            logical_span,
            cell_index=0,
            source_ranges=source_ranges,
        )


def test_notebook_scanner_reports_unmappable_parsed_source_as_input_error() -> None:
    document = _notebook([_markdown_cell("See {eq}`missing`.\n")])
    scanner = NotebookScanner()
    parsed = scanner.parse(document)

    result = scanner.scan(
        document,
        Config(),
        parsed=replace(parsed, cell_source_ranges=((),)),
    )

    assert result.blocks == ()
    assert result.labels == ()
    assert result.references == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["INP001"]
    assert result.diagnostics[0].detail == "notebook cell 0 source has no character ranges"


def test_notebook_source_list_items_remain_valid_when_facts_do_not_cross_boundary() -> None:
    document = _notebook(
        [
            _markdown_cell(
                [
                    "$$\nx = 1\n$$\n",
                    "See {eq}`missing`.\n",
                ]
            )
        ]
    )

    scan = NotebookScanner().scan(document, Config())

    assert len(scan.blocks) == 1
    assert len(scan.references) == 1
    assert scan.diagnostics == ()
    assert all(
        ', "' not in document.text[span.start : span.end]
        for span in (
            scan.blocks[0].span,
            scan.references[0].span,
        )
    )


def test_notebook_source_string_crlf_remains_contiguous() -> None:
    document = _notebook([_markdown_cell("$$x\r\ny$$")])

    scan = NotebookScanner().scan(document, Config())

    [block] = scan.blocks
    assert block.text == "x\ny"
    assert block.span is not None
    assert document.text[block.span.start : block.span.end] == r"x\r\ny"
    assert scan.diagnostics == ()


def test_notebook_source_string_standalone_cr_retains_its_json_span() -> None:
    document = _notebook([_markdown_cell("$$x\ry$$")])

    scan = NotebookScanner().scan(document, Config())

    [block] = scan.blocks
    assert block.text == "x\ny"
    assert block.span is not None
    assert document.text[block.span.start : block.span.end] == r"x\ry"
    assert scan.diagnostics == ()


def test_notebook_reference_before_trailing_standalone_cr_keeps_exact_span() -> None:
    document = _notebook([_markdown_cell("See {eq}`missing`.\r")])

    result = check_documents((document,), config=Config())

    [diagnostic] = result.diagnostics
    assert diagnostic.code == "REF002"
    assert diagnostic.span is not None
    assert diagnostic.span.cell_line == 1
    assert _raw_segments(document, diagnostic.span) == list("missing")


def test_notebook_reference_after_unicode_surrogate_pair_uses_raw_json_span() -> None:
    document = _notebook([_markdown_cell("😀 See {eq}`missing`.\n")])

    result = check_documents((document,), config=Config())

    assert r"\ud83d\ude00" in document.text
    [diagnostic] = [item for item in result.diagnostics if item.code == "REF002"]
    assert diagnostic.span is not None
    assert diagnostic.span.cell == 0
    assert document.text[diagnostic.span.start : diagnostic.span.end] == "missing"


@pytest.mark.parametrize(
    "raw_prefix",
    [r"\ud83dX", r"\ud83d\u0041"],
    ids=["unpaired-high-surrogate", "high-surrogate-before-non-low-escape"],
)
def test_notebook_reference_after_unpaired_surrogate_uses_raw_json_span(
    raw_prefix: str,
) -> None:
    text = (
        r'{"cells":[{"cell_type":"markdown","metadata":{},"source":"'
        + raw_prefix
        + r' See {eq}`missing`.\n"}],"metadata":{},"nbformat":4,"nbformat_minor":5}'
    )
    document = SourceDocument.from_text(
        PurePosixPath("surrogate.ipynb"),
        text,
        DocumentKind.NOTEBOOK,
    )

    result = check_documents((document,), config=Config())

    assert raw_prefix in document.text
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF002"]
    [diagnostic] = result.diagnostics
    assert diagnostic.span is not None
    assert diagnostic.span.cell == 0
    assert document.text[diagnostic.span.start : diagnostic.span.end] == "missing"


def test_notebook_empty_math_fence_maps_zero_width_raw_span() -> None:
    document = _notebook([_markdown_cell("```math\n```\n")])

    scan = NotebookScanner().scan(document, Config())

    [block] = scan.blocks
    assert block.text == ""
    assert block.span.start == block.span.end
    assert document.text[block.span.start : block.span.end] == ""
    assert block.span.cell == 0
    assert block.span.cell_line == 2
    assert scan.diagnostics == ()


def test_public_notebook_split_crlf_source_items_remain_analyzable() -> None:
    document = _notebook([_markdown_cell(["$$x\r", "\ny$$"])])

    scan = NotebookScanner().scan(document, Config())
    result = check_documents([document], config=Config())

    assert scan.blocks, "valid source-list cell should remain analyzable"
    [block] = scan.blocks
    assert block.text == "x\ny"
    assert block.span.segments
    assert len(block.span.segments[1].ranges) == 2
    assert _raw_segments(document, block.span) == ["x", r"\r", r"\n", "y"]
    assert scan.labels == ()
    assert scan.references == ()
    assert scan.symbol_directives == ()
    assert scan.diagnostics == ()
    assert result.diagnostics == ()
    assert result.math_blocks_checked == 1


def test_notebook_source_list_boundary_keeps_the_complete_math_block() -> None:
    document = _notebook(
        [
            _markdown_cell(
                [
                    "$$\nx = ",
                    "1\n$$\n",
                ]
            )
        ]
    )

    scan = NotebookScanner().scan(document, Config())
    result = check_documents([document], config=Config())

    assert scan.blocks, "valid source-list cell should remain analyzable"
    [block] = scan.blocks
    assert block.text == "x = 1"
    assert _raw_segments(document, block.span) == ["x", " ", "=", " ", "1"]
    assert ', "' in document.text[block.span.start : block.span.end]
    assert scan.labels == ()
    assert scan.references == ()
    assert scan.symbol_directives == ()
    assert scan.diagnostics == ()
    assert result.diagnostics == ()
    assert result.math_blocks_checked == 1


@pytest.mark.public_regression
def test_notebook_algebra_span_uses_exact_segments_across_source_items() -> None:
    document = _notebook([_markdown_cell(["$$x = ", "x + 1\n$$"])])

    result = check_documents([document], config=Config())

    first_start = document.text.index("x = ")
    second_start = document.text.index("x + 1")
    [diagnostic] = result.diagnostics
    assert (
        diagnostic.code,
        diagnostic.severity,
        diagnostic.message,
        diagnostic.equation,
        diagnostic.detail,
        diagnostic.hint,
        diagnostic.rule,
        diagnostic.suppressed,
        diagnostic.suppression_reason,
        diagnostic.profile,
        diagnostic.provenance_ids,
        diagnostic.properties,
    ) == (
        "ALG001",
        Severity.ERROR,
        "algebraic identity does not hold",
        "x = x + 1",
        "left - right = -1",
        None,
        "algebra",
        False,
        None,
        None,
        (),
        (),
    )
    span = diagnostic.span
    assert span is not None
    assert (
        span.path,
        span.start,
        span.end,
        span.line,
        span.col,
        span.end_line,
        span.end_col,
        span.cell,
        span.cell_line,
    ) == (
        document.path,
        first_start,
        second_start + 5,
        1,
        first_start + 1,
        1,
        second_start + 5,
        0,
        1,
    )
    assert _raw_segments(document, span) == list("x = x + 1")
    assert ', "' in document.text[first_start : second_start + 5]
    assert result.files_checked == 1
    assert result.math_blocks_checked == 1
    assert result.exit_code() == 1


def test_notebook_code_cells_are_ignored() -> None:
    document = _notebook(
        [
            _code_cell("raise RuntimeError('not executed')\n"),
            _code_cell("$$\n(a+b)^2 = a^2 + b^2\n$$\n"),
            _code_cell(["$$x\r", "\ny$$"]),
        ]
    )

    result = check_documents([document], config=Config())

    assert result.math_blocks_checked == 0
    assert result.diagnostics == ()


def test_notebook_scanner_rejects_parsed_input_from_another_document() -> None:
    first = _notebook([_markdown_cell("$$x = x$$")])
    second = _notebook([_markdown_cell("$$y = y$$")])
    scanner = NotebookScanner()
    parsed = scanner.parse(first)

    assert len(scanner.scan(first, Config(), parsed=parsed).blocks) == 1
    with pytest.raises(ValueError, match="different SourceDocument"):
        scanner.scan(second, Config(), parsed=parsed)


@pytest.mark.parametrize("text", ["{", "", " \n\t", "{} {}"])
def test_invalid_notebook_json_emits_input_diagnostic(text: str) -> None:
    document = SourceDocument.from_text(PurePosixPath("broken.ipynb"), text, DocumentKind.NOTEBOOK)

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["INP001"]
    assert result.diagnostics[0].span is not None
    assert result.diagnostics[0].span.path == PurePosixPath("broken.ipynb")


def test_oversized_notebook_input_fails_closed_before_json_decoding() -> None:
    text = "{}" + " " * DEFAULT_MAX_FILE_BYTES
    document = SourceDocument.from_text(PurePosixPath("huge.ipynb"), text, DocumentKind.NOTEBOOK)

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["INP003"]
    assert result.diagnostics[0].message == "input exceeds fixed safety limit"
    assert result.diagnostics[0].detail == (
        f"normalized notebook text exceeds {DEFAULT_MAX_FILE_BYTES} UTF-8 bytes"
    )
    assert result.math_blocks_checked == 0


def test_notebook_byte_limit_uses_normalized_source_document_text() -> None:
    raw_text = (" \r\n" * 400_000) + "{}"
    document = SourceDocument.from_text(
        PurePosixPath("normalized.ipynb"),
        raw_text,
        DocumentKind.NOTEBOOK,
    )

    assert len(raw_text.encode("utf-8")) > DEFAULT_MAX_FILE_BYTES
    assert len(document.text.encode("utf-8")) < DEFAULT_MAX_FILE_BYTES
    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["INP002"]
    assert result.math_blocks_checked == 0


def test_notebook_source_character_budget_fails_closed_before_mapping() -> None:
    from scieqlint.io.limits import DEFAULT_MAX_NOTEBOOK_SOURCE_CHARS

    source = "x" * (DEFAULT_MAX_NOTEBOOK_SOURCE_CHARS // 2 + 1)
    document = _notebook([_markdown_cell(source), _markdown_cell(source)])

    assert len(document.text.encode("utf-8")) < DEFAULT_MAX_FILE_BYTES
    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["INP003"]
    assert result.diagnostics[0].message == "input exceeds fixed safety limit"
    assert result.diagnostics[0].detail == (
        "normalized notebook Markdown source exceeds "
        f"{DEFAULT_MAX_NOTEBOOK_SOURCE_CHARS} logical characters"
    )
    assert result.math_blocks_checked == 0


def test_deeply_nested_notebook_input_fails_closed_without_recursion_error() -> None:
    text = "[" * 100_000 + "]" * 100_000
    document = SourceDocument.from_text(PurePosixPath("deep.ipynb"), text, DocumentKind.NOTEBOOK)

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["INP001"]
    assert result.diagnostics[0].detail == "maximum JSON nesting depth exceeded"
    assert result.math_blocks_checked == 0


def test_oversized_notebook_integer_emits_input_diagnostic_and_continues() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("huge.ipynb"),
        '{"cells":[],"metadata":{},"nbformat":' + "9" * 5000 + ',"nbformat_minor":0}',
        DocumentKind.NOTEBOOK,
    )
    later = SourceDocument.from_text(
        PurePosixPath("later.md"),
        "$$\nx = x + 1\n$$\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document, later], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["INP001", "ALG001"]
    assert result.diagnostics[0].detail
    assert result.diagnostics[0].span is not None
    assert result.diagnostics[0].span.path == PurePosixPath("huge.ipynb")


def test_oversized_notebook_integer_ignores_interpreter_digit_limit() -> None:
    previous_limit = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(0)
    try:
        document = SourceDocument.from_text(
            PurePosixPath("huge.ipynb"),
            '{"cells":[],"metadata":{},"nbformat":' + "9" * 5000 + ',"nbformat_minor":0}',
            DocumentKind.NOTEBOOK,
        )

        result = check_documents([document], config=Config())
    finally:
        sys.set_int_max_str_digits(previous_limit)

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["INP001"]
    assert result.diagnostics[0].detail == "JSON integer exceeds 4096 digits"


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nonstandard_notebook_json_constants_fail_closed(constant: str) -> None:
    document = SourceDocument.from_text(
        PurePosixPath("nonstandard.ipynb"),
        '{"cells":[],"metadata":{},"nbformat":' + constant + ',"nbformat_minor":0}',
        DocumentKind.NOTEBOOK,
    )

    result = check_documents([document], config=Config())

    [diagnostic] = result.diagnostics
    assert diagnostic.code == "INP001"
    assert diagnostic.detail == f"non-standard JSON constant is not supported: {constant}"
    assert diagnostic.span is not None
    assert diagnostic.span.path == document.path
    assert result.math_blocks_checked == 0


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


def test_notebook_nonlist_cells_fail_without_partial_scan() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("broken.ipynb"),
        json.dumps(
            {
                "cells": {},
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        DocumentKind.NOTEBOOK,
    )

    result = check_documents((document,), config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["INP002"]
    assert result.diagnostics[0].detail == "notebook cells must be a list"
    assert result.math_blocks_checked == 0


def test_notebook_invalid_metadata_and_cell_do_not_drop_later_readable_cell() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("recoverable.ipynb"),
        json.dumps(
            {
                "cells": [None, _markdown_cell("$$\n(a+b)^2 = a^2 + b^2\n$$\n")],
                "metadata": [],
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        DocumentKind.NOTEBOOK,
    )

    result = check_documents((document,), config=Config())

    assert {
        diagnostic.detail for diagnostic in result.diagnostics if diagnostic.code == "INP002"
    } == {
        "notebook metadata must be an object",
        "cell 0 must be an object",
    }
    [cell_diagnostic] = [
        diagnostic
        for diagnostic in result.diagnostics
        if diagnostic.detail == "cell 0 must be an object"
    ]
    assert cell_diagnostic.span is not None
    assert cell_diagnostic.span.cell == 0
    [math_diagnostic] = [
        diagnostic for diagnostic in result.diagnostics if diagnostic.code == "ALG001"
    ]
    assert math_diagnostic.span is not None
    assert math_diagnostic.span.cell == 1
    assert (
        document.text[math_diagnostic.span.start : math_diagnostic.span.end]
        == "(a+b)^2 = a^2 + b^2"
    )
    assert result.math_blocks_checked == 1


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


@pytest.mark.parametrize(
    "malformed_source",
    [[1], 7],
    ids=["non-string-list", "integer"],
)
def test_malformed_markdown_cell_source_emits_schema_warning_and_continues(
    malformed_source: object,
) -> None:
    document = _notebook(
        [
            {"cell_type": "markdown", "metadata": {}, "source": malformed_source},
            _markdown_cell(["$$\nE = m c^2\n$$\n"]),
        ]
    )

    result = check_documents([document], config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["INP002"]
    assert result.diagnostics[0].detail == "markdown cell 0 source must be a string or string list"
    assert result.diagnostics[0].span is not None
    assert result.diagnostics[0].span.cell == 0
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


def test_notebook_symbol_directives_preserve_cell_metadata() -> None:
    document = _notebook(
        [
            _markdown_cell("introductory text\n"),
            _markdown_cell("<!-- scieqlint-symbol: x = variable -->\n$$\nx = x\n$$\n"),
        ]
    )

    result = check_documents(
        [document],
        config=Config(checks=ChecksConfig(symbols=SymbolsConfig(enabled=True))),
    )

    assert result.files_checked == 1
    assert result.math_blocks_checked == 1
    assert result.exit_code() == 0
    assert result.diagnostics == ()
    scan = NotebookScanner().scan(document, Config())
    assert [
        (directive.symbol, directive.span.cell, directive.span.cell_line)
        for directive in scan.symbol_directives
    ] == [("x", 1, 1)]


def test_notebook_symbol_directive_has_active_undefined_symbol_control() -> None:
    cell_source = "<!-- scieqlint-symbol: x = variable -->\n$$\ny = y\n$$\n"
    document = _notebook(
        [
            _markdown_cell("introductory text\n"),
            _markdown_cell(cell_source),
        ]
    )

    result = check_documents(
        [document],
        config=Config(checks=ChecksConfig(symbols=SymbolsConfig(enabled=True))),
    )

    assert result.files_checked == 1
    assert result.math_blocks_checked == 1
    assert result.exit_code() == 0
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "SYM001"
    assert result.diagnostics[0].severity is Severity.WARNING
    assert result.diagnostics[0].message == "undefined symbol: y"
    span = result.diagnostics[0].span
    assert span is not None
    assert span.path == PurePosixPath("notes.ipynb")
    assert span.cell == 1
    assert span.cell_line == 3
    symbol_start = document.text.index("y = y")
    line, col = document.line_index.position(symbol_start)
    assert (span.start, span.end, span.line, span.col, span.end_line, span.end_col) == (
        symbol_start,
        symbol_start + 1,
        line,
        col,
        line,
        col,
    )
    assert len(span.segments) == 1
    assert span.segments[0].ranges == ((symbol_start, symbol_start + 1),)
    assert (span.segments[0].line, span.segments[0].col) == (line, col)
    assert document.text[span.start : span.end] == "y"


def test_notebook_symbol_diagnostic_keeps_raw_location_in_all_reporters() -> None:
    document = _notebook(
        [_markdown_cell("<!-- scieqlint-symbol: x = variable -->\n$$\nx = 1\ny = y\n$$")]
    )
    result = check_documents(
        [document],
        config=Config(checks=ChecksConfig(symbols=SymbolsConfig(enabled=True))),
    )

    [diagnostic] = result.diagnostics
    assert diagnostic.code == "SYM001"
    assert diagnostic.span is not None
    span = diagnostic.span
    location = f"notes.ipynb:{span.line}:{span.col}"
    assert location in TextReporter().render(result)

    [json_diagnostic] = json.loads(JsonReporter().render(result))["diagnostics"]
    assert {
        key: json_diagnostic[key]
        for key in ("path", "line", "col", "end_line", "end_col", "cell", "cell_line")
    } == {
        "path": "notes.ipynb",
        "line": span.line,
        "col": span.col,
        "end_line": span.end_line,
        "end_col": span.end_col,
        "cell": 0,
        "cell_line": span.cell_line,
    }
    assert "segments" not in json_diagnostic

    github = GitHubReporter().render(result)
    assert (
        f"file=notes.ipynb,line={span.line},col={span.col},"
        f"endLine={span.end_line},endColumn={span.end_col}"
    ) in github

    sarif = json.loads(SarifReporter().render(result))
    region = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]
    assert region == {
        "startLine": span.line,
        "startColumn": span.col,
        "endLine": span.end_line,
        "endColumn": span.end_col + 1,
    }


def test_duplicate_notebook_symbol_directives_keep_each_cell_identity() -> None:
    document = _notebook(
        [
            _markdown_cell("<!-- scieqlint-symbol: x = first -->\n"),
            _markdown_cell("intro\n<!-- scieqlint-symbol: x = second -->\n"),
        ]
    )

    scan = NotebookScanner().scan(document, Config())

    assert [
        (directive.symbol, directive.span.cell, directive.span.cell_line)
        for directive in scan.symbol_directives
    ] == [
        ("x", 0, 1),
        ("x", 1, 2),
    ]


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


def _code_cell(source: str | list[str]) -> dict[str, object]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source,
    }


def _raw_segments(document: SourceDocument, span: SourceSpan) -> list[str]:
    segments = getattr(span, "segments", ())
    assert segments
    return [document.text[start:end] for segment in segments for start, end in segment.ranges]
