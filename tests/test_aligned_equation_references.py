from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pytest

from scieqlint.api import check_documents
from scieqlint.config.model import AlgebraConfig, ChecksConfig, Config, ScannerConfig
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.parse.math import MathHost
from scieqlint.query.host import QueryHost
from scieqlint.scan.notebook import NotebookScanner

FENCED_FIXTURE = Path("tests/fixtures/good/aligned_equation_references.md")


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("aligned.md"),
        text,
        DocumentKind.MARKDOWN,
    )


def without_algebra() -> Config:
    return Config(checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)))


def lower(document: SourceDocument):
    return MathHost().classify(MySTFrontend().lower((document,)))


def fixture_doc(path: Path) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath(path.as_posix()),
        path.read_text(encoding="utf-8"),
        DocumentKind.MARKDOWN,
    )


@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_math_directive_options_do_not_create_tex_references(newline: str) -> None:
    source = newline.join(
        (
            "```{math}",
            ":label: actual",
            r":alt: The literal \ref{example} or \eqref{example}.",
            "",
            "x = x",
            "```",
            "",
            "See {eq}`actual`.",
            "",
        )
    )

    result = check_documents((doc(source),), config=Config())

    assert result.diagnostics == ()
    assert result.math_blocks_checked == 1


@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_math_directive_option_labels_are_not_equation_targets(newline: str) -> None:
    source = newline.join(
        (
            "```{math}",
            ":label: explicit",
            r":alt: The literal \label{example}.",
            r"x = x \label{body}",
            "```",
            "",
            "See {eq}`example`, {eq}`explicit`, and {eq}`body`.",
            "",
        )
    )

    result = check_documents((doc(source),), config=Config())

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF002"]
    diagnostic = result.diagnostics[0]
    assert diagnostic.message == "equation reference target not found: example"
    assert diagnostic.span is not None
    start = source.replace("\r\n", "\n").rindex("example")
    assert (diagnostic.span.start, diagnostic.span.end) == (start, start + len("example"))
    assert result.math_blocks_checked == 1


def test_aligned_display_models_labels_internal_refs_and_paragraph_start_refs() -> None:
    source = """\
$$
\\begin{align}
a &= b \\label{eq:first} \\\\
c &= d \\eqref{eq:first}
\\end{align}
$$

{eq}`eq:first` begins the next paragraph.
"""

    snapshot = lower(doc(source))
    query = QueryHost(snapshot)

    assert [(fact.container, fact.label_fact_ids) for fact in snapshot.display_math] == [
        ("ams", (snapshot.equation_labels[0].fact_id,))
    ]
    assert [(fact.label, fact.label_syntax_kind) for fact in snapshot.equation_labels] == [
        ("eq:first", "tex-label")
    ]
    assert [
        (fact.ref_kind, fact.target, fact.source_block_id) for fact in snapshot.equation_refs
    ] == [
        ("tex-eqref", "eq:first", snapshot.display_math[0].fact_id),
        ("eq", "eq:first", None),
    ]
    assert query.references.unresolved_equation_refs() == ()
    assert ReferenceEngine().run(query) == ()
    assert all(fact.target_span is not None for fact in snapshot.equation_refs)
    assert [
        source[fact.target_span.start : fact.target_span.end]
        for fact in snapshot.equation_refs
        if fact.target_span is not None
    ] == ["eq:first", "eq:first"]


def test_missing_tex_reference_inside_aligned_display_has_one_exact_public_diagnostic() -> None:
    source = """\
$$
\\begin{align}
x &= \\eqref{missing}
\\end{align}
$$
"""
    document = doc(source)

    snapshot = lower(document)
    engine = ReferenceEngine().run(QueryHost(snapshot))
    result = check_documents([document], config=without_algebra())
    reference_diagnostics = tuple(
        diagnostic for diagnostic in result.diagnostics if diagnostic.code.startswith("REF")
    )

    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-eqref", "missing")
    ]

    assert [(diagnostic.code, diagnostic.detail) for diagnostic in engine] == [
        ("REF002", r"reference text: \eqref{missing}")
    ]
    assert [(diagnostic.code, diagnostic.detail) for diagnostic in reference_diagnostics] == [
        ("REF002", r"reference text: \eqref{missing}")
    ]
    assert reference_diagnostics[0].span is not None
    assert (
        source[reference_diagnostics[0].span.start : reference_diagnostics[0].span.end] == "missing"
    )


def test_same_path_cross_kind_labels_preserve_scanner_ownership() -> None:
    markdown = SourceDocument.from_text(
        PurePosixPath("same.md"),
        "$$\nx = 1 \\label{md}\n$$\n\n{eq}`tex`\n",
        DocumentKind.MARKDOWN,
    )
    latex = SourceDocument.from_text(
        PurePosixPath("same.md"),
        "\\begin{equation}\ny = 2 \\label{tex}\n\\end{equation}\n",
        DocumentKind.LATEX,
    )

    result = check_documents((markdown, latex), config=without_algebra())

    reference_codes = [
        diagnostic.code for diagnostic in result.diagnostics if diagnostic.code.startswith("REF")
    ]
    assert reference_codes == []


def test_duplicate_aligned_labels_report_declaration_and_reference_ambiguity() -> None:
    source = """\
$$
\\begin{align}
a &= b \\label{dup}
\\end{align}
$$

$$
\\begin{align}
c &= d \\label{dup}
\\end{align}
$$

{eq}`dup`
"""
    document = doc(source)

    snapshot = lower(document)
    query = QueryHost(snapshot)
    engine = ReferenceEngine().run(query)
    result = check_documents([document], config=without_algebra())

    assert query.references.duplicate_equation_targets() == {"dup": snapshot.equation_labels}
    assert [(diagnostic.code, diagnostic.message) for diagnostic in engine] == [
        ("REF001", "duplicate equation label: dup"),
        ("REF011", "ambiguous equation reference: dup"),
    ]
    assert [diagnostic.code for diagnostic in result.diagnostics].count("REF001") == 1
    assert [diagnostic.code for diagnostic in result.diagnostics].count("REF011") == 1
    assert query.references.ambiguous_equation_refs() == (snapshot.equation_refs[0],)


def test_latex_reference_diagnostics_do_not_depend_on_markdown_scanning() -> None:
    source = (
        "\\begin{equation}\nx = 1 \\label{dup}\n\\end{equation}\n"
        "\\begin{equation}\ny = 2 \\label{dup}\n\\end{equation}\n"
        "See \\eqref{dup} and \\eqref{absent}.\n"
    )
    document = SourceDocument.from_text(PurePosixPath("aligned.tex"), source, DocumentKind.LATEX)
    expected_starts = [
        source.index("dup", source.index("dup") + 1),
        source.rindex("dup"),
        source.index("absent"),
    ]

    for markdown in (True, False):
        config = Config(scanner=ScannerConfig(markdown=markdown))
        result = check_documents((document,), config=config)

        assert [diagnostic.code for diagnostic in result.diagnostics] == [
            "REF001",
            "REF011",
            "REF002",
        ]
        assert [
            diagnostic.span.start for diagnostic in result.diagnostics if diagnostic.span
        ] == expected_starts
        assert [
            source[diagnostic.span.start : diagnostic.span.end]
            for diagnostic in result.diagnostics
            if diagnostic.span
        ] == ["dup", "dup", "absent"]
        assert (result.files_checked, result.math_blocks_checked) == (1, 2)
        if not markdown:
            with_disabled_markdown = check_documents(
                (document, doc("See {eq}`markdown-only`.\n")), config=config
            )
            assert with_disabled_markdown.diagnostics == result.diagnostics
            assert (
                with_disabled_markdown.files_checked,
                with_disabled_markdown.math_blocks_checked,
            ) == (2, 2)


def test_aligned_rows_retain_the_enclosing_display_as_the_owner() -> None:
    source = r"""$$
\begin{align}
a &= b \label{eq:row-a} \\
c &= d \label{eq:row-c} \\
e &= f \eqref{eq:row-a} + \eqref{eq:row-c}
\end{align}
$$
"""

    snapshot = lower(doc(source))
    display = snapshot.display_math[0]
    labels = snapshot.equation_labels
    references = snapshot.equation_refs

    assert display.container == "ams"
    assert display.environment == "align"
    assert display.label_fact_ids == tuple(label.fact_id for label in labels)
    assert {label.source_block_id for label in labels} == {display.fact_id}
    assert {reference.source_block_id for reference in references} == {display.fact_id}
    assert [(label.label, source[label.span.start : label.span.end]) for label in labels] == [
        ("eq:row-a", "eq:row-a"),
        ("eq:row-c", "eq:row-c"),
    ]


def test_fenced_myst_math_fixture_models_aligned_labels_and_references() -> None:
    document = fixture_doc(FENCED_FIXTURE)
    snapshot = lower(document)
    query = QueryHost(snapshot)

    assert [(fact.container, fact.complete) for fact in snapshot.display_math] == [("ams", True)]
    assert snapshot.display_math[0].environment == "align"
    assert [label.label for label in snapshot.equation_labels] == [
        "eq:row-a",
        "eq:row-c",
        "eq:fenced",
    ]
    assert [reference.target for reference in snapshot.equation_refs] == [
        "eq:fenced",
        "eq:row-a",
        "eq:row-c",
    ]
    assert ReferenceEngine().run(query) == ()


@pytest.mark.public_regression
def test_public_reference_path_has_one_canonical_diagnostic_across_source_kinds() -> None:
    markdown_source = "$$\nx = 1 \\label{dup}\n$$\n\nSee {eq}`dup`.\n"
    markdown = SourceDocument.from_text(
        PurePosixPath("z.md"),
        markdown_source,
        DocumentKind.MARKDOWN,
    )
    latex = SourceDocument.from_text(
        PurePosixPath("a.tex"),
        "\\begin{equation}\ny = 2 \\label{dup}\n\\end{equation}\n",
        DocumentKind.LATEX,
    )

    result = check_documents((markdown, latex), config=without_algebra())
    reversed_result = check_documents((latex, markdown), config=without_algebra())

    expected = [
        (
            "REF001",
            "duplicate equation label: dup",
            "z.md",
            markdown_source.index("dup"),
            markdown_source.index("dup") + 3,
        ),
        (
            "REF011",
            "ambiguous equation reference: dup",
            "z.md",
            markdown_source.rindex("dup"),
            markdown_source.rindex("dup") + 3,
        ),
    ]

    def diagnostic_contract(result):
        return [
            (
                diagnostic.code,
                diagnostic.message,
                diagnostic.span.path.as_posix() if diagnostic.span else None,
                diagnostic.span.start if diagnostic.span else None,
                diagnostic.span.end if diagnostic.span else None,
            )
            for diagnostic in result.diagnostics
            if diagnostic.code.startswith("REF")
        ]

    assert diagnostic_contract(result) == expected
    assert diagnostic_contract(reversed_result) == expected


def test_public_duplicate_diagnostic_uses_normalized_label_text() -> None:
    source = "$$\nx = 1 \\label{dup}\n$$\n$$\ny = 2 \\label{ dup }\n$$\n"
    document = SourceDocument.from_text(
        PurePosixPath("normalized.md"),
        source,
        DocumentKind.MARKDOWN,
    )

    result = check_documents((document,), config=without_algebra())

    duplicate = [diagnostic for diagnostic in result.diagnostics if diagnostic.code == "REF001"]
    assert [
        (
            diagnostic.message,
            diagnostic.span.path.as_posix() if diagnostic.span else None,
            diagnostic.span.start if diagnostic.span else None,
            diagnostic.span.end if diagnostic.span else None,
        )
        for diagnostic in duplicate
    ] == [
        (
            "duplicate equation label: dup",
            "normalized.md",
            source.index(" dup "),
            source.index(" dup ") + 5,
        )
    ]


def test_notebook_fact_ids_and_source_keys_include_cell_identity() -> None:
    from scieqlint.app import _legacy_equation_label_fact
    from scieqlint.engine.reference import _fact_source_key

    source = "$$\nx = 1 \\label{same}\n$$\n"
    document = SourceDocument.from_text(
        PurePosixPath("notes.ipynb"),
        json.dumps(
            {
                "cells": [
                    {"cell_type": "markdown", "metadata": {}, "source": source},
                    {"cell_type": "markdown", "metadata": {}, "source": source},
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        DocumentKind.NOTEBOOK,
    )

    scan = NotebookScanner().scan(document, Config())
    facts = tuple(_legacy_equation_label_fact(label) for label in scan.labels)

    assert [fact.span.cell for fact in facts if fact.span is not None] == [0, 1]
    assert len({fact.fact_id for fact in facts}) == 2
    assert all(f"::cell-{cell}" in fact.fact_id for fact, cell in zip(facts, (0, 1), strict=True))
    assert [_fact_source_key(fact)[:2] for fact in facts] == [
        ("notes.ipynb", 0),
        ("notes.ipynb", 1),
    ]


@pytest.mark.public_regression
def test_notebook_reference_path_reports_duplicate_and_ambiguous_targets_by_cell() -> None:
    label_source = "$$\nx = 1 \\label{same}\n$$\n"
    reference_source = "See {eq}`same`.\n"
    document = SourceDocument.from_text(
        PurePosixPath("references.ipynb"),
        json.dumps(
            {
                "cells": [
                    {"cell_type": "markdown", "metadata": {}, "source": label_source},
                    {"cell_type": "markdown", "metadata": {}, "source": label_source},
                    {"cell_type": "markdown", "metadata": {}, "source": reference_source},
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        DocumentKind.NOTEBOOK,
    )

    result = check_documents((document,), config=without_algebra())

    assert [
        (
            diagnostic.code,
            diagnostic.message,
            diagnostic.span.cell if diagnostic.span else None,
            diagnostic.span.start if diagnostic.span else None,
            diagnostic.span.end if diagnostic.span else None,
        )
        for diagnostic in result.diagnostics
        if diagnostic.code.startswith("REF")
    ] == [
        ("REF001", "duplicate equation label: same", 1, 16, 20),
        ("REF011", "ambiguous equation reference: same", 2, 9, 13),
    ]


def test_reference_engine_output_is_independent_of_document_input_order() -> None:
    first = doc("See {eq}`missing-z`.\n")
    first = SourceDocument.from_text(PurePosixPath("z.md"), first.text, DocumentKind.MARKDOWN)
    second = SourceDocument.from_text(
        PurePosixPath("a.md"),
        "See {eq}`missing-a`.\n",
        DocumentKind.MARKDOWN,
    )

    def engine_output(documents):
        from scieqlint.parse.math import MathHost

        snapshot = MathHost().classify(MySTFrontend().lower(documents))
        return ReferenceEngine().run(QueryHost(snapshot))

    forward = engine_output((first, second))
    reverse = engine_output((second, first))

    assert [
        (diagnostic.code, diagnostic.message, diagnostic.span.path.as_posix())
        for diagnostic in forward
    ] == [
        ("REF002", "equation reference target not found: missing-a", "a.md"),
        ("REF002", "equation reference target not found: missing-z", "z.md"),
    ]
    assert reverse == forward


def test_tex_reference_scanning_is_container_bounded_and_source_ordered() -> None:
    source = """\
```text
$$
\\begin{align}
x &= \\eqref{code-only}
\\end{align}
$$
```

$$
\\begin{align}
a &= \\ref{first} \\\\
b &= \\eqref{second}
\\end{align}
$$
"""

    snapshot = lower(doc(source))

    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-ref", "first"),
        ("tex-eqref", "second"),
    ]
    assert [
        fact.target_span.start for fact in snapshot.equation_refs if fact.target_span
    ] == sorted(fact.target_span.start for fact in snapshot.equation_refs if fact.target_span)


def test_dollar_math_ignores_escaped_environment_and_reference_tokens() -> None:
    source = r"""$$
\\begin{align}
x &= \\ref{escaped} + \ref{ } + \ref{valid}
\\end{align}
$$"""

    snapshot = lower(doc(source))

    assert snapshot.display_math[0].container == "dollar-dollar"
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-ref", "valid")
    ]


def test_aligned_math_ignores_active_tex_comments_for_environment_labels_and_refs() -> None:
    source = r"""$$
% \begin{align}
x &= y % \label{commented} \eqref{commented}
\label{real}
\eqref{missing}
% \end{align}
$$"""

    snapshot = lower(doc(source))

    assert [(fact.container, fact.environment) for fact in snapshot.display_math] == [
        ("dollar-dollar", None)
    ]
    assert [fact.label for fact in snapshot.equation_labels] == ["real"]
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-eqref", "missing")
    ]


def test_incomplete_aligned_environment_keeps_display_identity_without_ams_claim() -> None:
    source = """\
$$
\\begin{align}
x &= \\eqref{missing}
$$
"""

    snapshot = lower(doc(source))

    assert [fact.container for fact in snapshot.display_math] == ["dollar-dollar"]
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-eqref", "missing")
    ]


def test_incomplete_math_fence_does_not_create_equation_semantics() -> None:
    source = "```math\nx = \\eqref{missing} \\label{ghost}\n"

    snapshot = lower(doc(source))

    assert [(fact.container, fact.complete) for fact in snapshot.display_math] == [
        ("fenced-math", False)
    ]
    assert snapshot.equation_labels == ()
    assert snapshot.equation_refs == ()


def test_blank_tex_labels_are_not_equation_targets() -> None:
    source = "$$\nx = 1 \\label{ } \\label{live}\n$$\n"

    snapshot = lower(doc(source))

    assert [fact.label for fact in snapshot.equation_labels] == ["live"]


def test_mismatched_nested_ams_environment_is_not_classified() -> None:
    source = r"""$$
\begin{align}
a &= b
\begin{gather}
c &= d
\end{align}
$$
"""

    snapshot = lower(doc(source))

    assert [(fact.container, fact.environment) for fact in snapshot.display_math] == [
        ("dollar-dollar", None)
    ]


def test_unclosed_outer_same_name_ams_environment_is_not_classified() -> None:
    source = r"""$$
\begin{align}
a &= b
\begin{align}
c &= d
\end{align}
$$
"""

    snapshot = lower(doc(source))

    assert [(fact.container, fact.environment) for fact in snapshot.display_math] == [
        ("dollar-dollar", None)
    ]


def test_properly_nested_ams_environment_remains_classified() -> None:
    source = r"""$$
\begin{align}
a &= b
\begin{aligned}
c &= d
\end{aligned}
\end{align}
$$
"""

    snapshot = lower(doc(source))

    assert [(fact.container, fact.environment) for fact in snapshot.display_math] == [
        ("ams", "align")
    ]


def test_custom_environment_names_participate_in_ams_nesting() -> None:
    malformed = (
        r"\begin{align}\begin{my-env:foo}x=1\end{align}",
        (
            r"\begin{align}\begin{my-env:foo}x=1\end{other-env}"
            r"\end{my-env:foo}\end{align}"
        ),
    )
    for body in malformed:
        snapshot = lower(doc(f"$$\n{body}\n$$\n"))
        assert [(fact.container, fact.environment) for fact in snapshot.display_math] == [
            ("dollar-dollar", None)
        ]

    valid = lower(
        doc(
            "$$\n"
            r"\begin{align}\begin{my-env:foo}x=1\end{my-env:foo}\end{align}"
            "\n$$\n"
        )
    )
    assert [(fact.container, fact.environment) for fact in valid.display_math] == [("ams", "align")]
