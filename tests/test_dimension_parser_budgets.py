from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from scieqlint.api import check_documents
from scieqlint.config.load import load_config
from scieqlint.io.source import DocumentKind, SourceDocument


@pytest.mark.public_regression
def test_dimension_budgets_report_typed_diagnostics_and_continue(tmp_path: Path) -> None:
    config = _dimension_config(tmp_path, aliases=(r"\m",))
    numeric_detail = (
        "dimension expression exceeds the supported numeric-component budget of 512 decimal digits"
    )
    nesting_detail = "dimension expression exceeds the supported group-nesting budget of 64"
    cases = (
        ("01-digits.md", rf"\m^{'9' * 5_000}=\m"),
        ("02-groups.md", rf"\m*{'(' * 400}x{')' * 400}=x"),
        ("03-control.md", "x=t"),
    )
    sources = tuple((path, f"$$\n{equation}\n$$\n", equation) for path, equation in cases)

    try:
        result = check_documents(
            [_document(path, source) for path, source, _ in sources],
            config=config,
        )
    except (ValueError, RecursionError) as exc:
        pytest.fail(f"dimension checking leaked {type(exc).__name__}: {exc}")

    assert [
        (item.code, item.severity.value, item.message, item.detail, item.rule)
        for item in result.diagnostics
    ] == [
        ("DIM020", "info", "dimension check skipped", numeric_detail, "dimensions"),
        ("PARSE020", "info", "unsupported syntax; check skipped", None, "parser"),
        ("DIM020", "info", "dimension check skipped", nesting_detail, "dimensions"),
        ("PARSE020", "info", "unsupported syntax; check skipped", None, "parser"),
        (
            "DIM001",
            "error",
            "equation sides have different dimensions",
            "left dimension L; right dimension T",
            "dimensions",
        ),
    ]
    assert result.files_checked == 3
    assert result.math_blocks_checked == 3
    assert result.exit_code() == 1

    dimension_diagnostics = tuple(item for item in result.diagnostics if item.rule == "dimensions")
    for diagnostic, (path, source, equation) in zip(dimension_diagnostics, sources, strict=True):
        span = diagnostic.span
        assert span is not None
        assert span.path == PurePosixPath(path)
        assert span.start == source.index(equation)
        assert span.end == span.start + len(equation)
        assert source[span.start : span.end] == equation
        assert (span.line, span.col, span.end_line, span.end_col) == (
            2,
            1,
            2,
            len(equation),
        )


@pytest.mark.parametrize(
    ("equation", "expected_detail"),
    [
        (
            f"x^{'9' * 513}=x",
            (
                "dimension expression exceeds the supported numeric-component budget "
                "of 512 decimal digits"
            ),
        ),
        (
            f"x {'9' * 513}/1=x",
            (
                "dimension expression exceeds the supported numeric-component budget "
                "of 512 decimal digits"
            ),
        ),
        (
            f"x 1/{'9' * 513}=x",
            (
                "dimension expression exceeds the supported numeric-component budget "
                "of 512 decimal digits"
            ),
        ),
    ],
    ids=[
        "513-digit-exponent",
        "513-digit-rational-numerator",
        "513-digit-rational-denominator",
    ],
)
def test_dimension_budget_rejects_first_unsupported_numeric_value(
    tmp_path: Path,
    equation: str,
    expected_detail: str,
) -> None:
    result = check_documents(
        [_document("outside-budget.md", f"$$\n{equation}\n$$\n")],
        config=_dimension_config(tmp_path),
    )

    assert [
        (item.code, item.detail) for item in result.diagnostics if item.rule == "dimensions"
    ] == [("DIM020", expected_detail)]


@pytest.mark.parametrize(
    ("opening", "closing"),
    [("(", ")"), ("{", "}")],
    ids=["65-parentheses", "65-braces"],
)
def test_dimension_budget_rejects_first_unsupported_group_depth(
    tmp_path: Path,
    opening: str,
    closing: str,
) -> None:
    equation = f"x*{opening * 65}x{closing * 65}=x"
    result = check_documents(
        [_document("outside-budget.md", f"$$\n{equation}\n$$\n")],
        config=_dimension_config(tmp_path),
    )

    assert [
        (item.code, item.detail) for item in result.diagnostics if item.rule == "dimensions"
    ] == [
        (
            "DIM020",
            "dimension expression exceeds the supported group-nesting budget of 64",
        )
    ]


def test_dimension_budget_boundaries_preserve_supported_inputs(tmp_path: Path) -> None:
    numeric_boundary = f"x^{'1' + '0' * 511}=x^{'1' + '0' * 511}"
    group_boundary = f"x*{'(' * 64}x{')' * 64}=x^2"
    for equation in (numeric_boundary, group_boundary):
        result = check_documents(
            [_document("boundary.md", f"$$\n{equation}\n$$\n")],
            config=_dimension_config(tmp_path),
        )

        dimension_diagnostics = tuple(
            item for item in result.diagnostics if item.rule == "dimensions"
        )
        assert dimension_diagnostics == (), equation


def test_numeric_budget_applies_to_tokens_not_identifier_suffixes(tmp_path: Path) -> None:
    identifier = "x" + "9" * 2_000
    result = check_documents(
        [_document("identifier.md", f"$$\n{identifier}={identifier}\n$$\n")],
        config=_dimension_config(tmp_path, ignore_unknowns=True),
    )

    assert result.diagnostics == ()


def test_numeric_budget_ignores_digits_inside_configured_aliases(tmp_path: Path) -> None:
    alias = "x" + "9" * 2_000
    result = check_documents(
        [_document("alias.md", f"$$\n{alias}={alias}\n$$\n")],
        config=_dimension_config(tmp_path, aliases=(alias,)),
    )

    assert result.diagnostics == ()


def test_long_unary_sign_chain_does_not_use_recursive_parser_frames(tmp_path: Path) -> None:
    equation = "+" * 2_000 + "x=x"
    result = check_documents(
        [_document("signs.md", f"$$\n{equation}\n$$\n")],
        config=_dimension_config(tmp_path),
    )

    assert result.diagnostics == ()


def test_existing_unsupported_dimension_skip_has_no_budget_detail(tmp_path: Path) -> None:
    result = check_documents(
        [_document("unsupported.md", "$$\nx @ x = x\n$$\n")],
        config=_dimension_config(tmp_path),
    )

    assert [
        (item.code, item.detail) for item in result.diagnostics if item.rule == "dimensions"
    ] == [("DIM020", None)]


def _dimension_config(
    tmp_path: Path,
    *,
    aliases: tuple[str, ...] = (),
    ignore_unknowns: bool = False,
):
    path = tmp_path / ("ignore.toml" if ignore_unknowns else "scieqlint.toml")
    lines = [
        "[checks.algebra]",
        "enabled = false",
        "",
        "[checks.dimension]",
        'mode = "on"',
    ]
    if ignore_unknowns:
        lines.append('unknown_variables = "ignore"')
    lines.extend(("", "[vars]", 'x = "L"', 't = "T"'))
    if aliases:
        values = ", ".join(_toml_string(alias) for alias in aliases)
        lines.extend(("", "[aliases]", f"x = [{values}]"))
    path.write_text("\n".join(lines), encoding="utf-8")
    return load_config(path)


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _document(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)
