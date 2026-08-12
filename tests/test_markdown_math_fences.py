from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from scieqlint.api import check_documents
from scieqlint.config.model import Config
from scieqlint.io.source import DocumentKind, SourceDocument


def _check(source: str):
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        source,
        DocumentKind.MARKDOWN,
    )
    return check_documents([document], config=Config())


@pytest.mark.parametrize("opener", ["```math", "```{math}"], ids=["math", "directive"])
def test_exact_triple_backtick_math_fence_remains_supported(opener: str) -> None:
    result = _check(f"{opener}\nx=x+1\n```\n")

    assert result.math_blocks_checked == 1
    assert [
        (
            diagnostic.code,
            diagnostic.span.line if diagnostic.span is not None else None,
            diagnostic.span.col if diagnostic.span is not None else None,
        )
        for diagnostic in result.diagnostics
    ] == [("ALG001", 2, 1)]


@pytest.mark.parametrize(
    ("opener", "closer"),
    [
        (" ~~~{math}\t", " ~~~~  "),
        ("  ````math", "  `````"),
        ("   ~~~~~{math}", "   ~~~~~"),
    ],
    ids=["tilde-longer-closer", "long-backtick", "three-space-indent"],
)
@pytest.mark.public_regression
def test_commonmark_math_fences_reach_math_checks(opener: str, closer: str) -> None:
    result = _check(f"{opener}\nx=x+1\n{closer}\n")

    assert result.math_blocks_checked == 1
    assert [
        (
            diagnostic.code,
            diagnostic.span.line if diagnostic.span is not None else None,
            diagnostic.span.col if diagnostic.span is not None else None,
        )
        for diagnostic in result.diagnostics
    ] == [("ALG001", 2, 1)]


@pytest.mark.parametrize(
    "source",
    [
        "    ```math\nx=x+1\n    ```\n",
        "~~~python\n$$\nx=x+1\n$$\n~~~\n",
        "````math`invalid\nx=x+1\n````\n",
    ],
    ids=["four-space-indent", "non-math-info", "backtick-in-info"],
)
def test_non_math_fence_forms_remain_inactive(source: str) -> None:
    result = _check(source)

    assert result.math_blocks_checked == 0
    assert result.diagnostics == ()


@pytest.mark.parametrize(
    ("opener", "closer"),
    [
        ("````math", "```"),
        ("````math", "~~~~"),
        ("````math", "    ````"),
        ("~~~~math", "~~~"),
        ("~~~~math", "````"),
    ],
    ids=[
        "shorter-backtick",
        "wrong-marker-tilde",
        "four-space-backtick",
        "shorter-tilde",
        "wrong-marker-backtick",
    ],
)
@pytest.mark.public_regression
def test_invalid_explicit_math_fence_closers_remain_unterminated(
    opener: str,
    closer: str,
) -> None:
    result = _check(f"{opener}\nx=x+1\n{closer}\n")

    assert result.math_blocks_checked == 0
    assert [
        (
            diagnostic.code,
            diagnostic.span.line if diagnostic.span is not None else None,
            diagnostic.span.col if diagnostic.span is not None else None,
        )
        for diagnostic in result.diagnostics
    ] == [("SCAN001", 1, 1)]


@pytest.mark.parametrize(
    "opener",
    ["~~~math", "  ````{math}"],
    ids=["tilde", "indented-backtick"],
)
@pytest.mark.public_regression
def test_unterminated_commonmark_math_fences_warn_at_the_opener(opener: str) -> None:
    result = _check(f"{opener}\nx=x+1\n")

    assert result.math_blocks_checked == 0
    assert [
        (
            diagnostic.code,
            diagnostic.span.line if diagnostic.span is not None else None,
            diagnostic.span.col if diagnostic.span is not None else None,
        )
        for diagnostic in result.diagnostics
    ] == [("SCAN001", 1, 1)]
