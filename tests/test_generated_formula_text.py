from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path, PurePosixPath

import pytest

from scieqlint.app import check_documents
from scieqlint.config.model import Config, ProfileConfig, ScannerConfig
from scieqlint.engine.generated import GeneratedOutputEngine
from scieqlint.facts.generated import GeneratedFormulaFact, GeneratedProvenanceFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.frontend.notebook import NotebookFrontend
from scieqlint.io.source import DocumentKind, SourceDocument, SourceOrigin
from scieqlint.parse.math import MathHost
from scieqlint.query.host import QueryHost
from scieqlint.report.text import TextReporter


def doc(text: str, *, origin: SourceOrigin | None = None) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("generated.md"),
        text,
        DocumentKind.MARKDOWN,
        origin=origin,
    )


def test_directive_options_are_not_generated_formula_content() -> None:
    for newline in ("\n", "\r\n"):
        source = newline.join(
            (
                "```{math}",
                ':typst: "/C0 apod"',
                r":alt: \A t t e n t {x}",
                "",
                "x = x",
                "```",
                "",
            )
        )

        result = check_documents(
            (doc(source),), config=Config(profile=ProfileConfig(name="generated-myst"))
        )

        assert result.diagnostics == ()
        assert result.math_blocks_checked == 1


def test_formula_artifact_after_directive_options_keeps_its_source_span() -> None:
    for newline in ("\n", "\r\n"):
        source = newline.join(("```{math}", ':typst: "/C0 apod"', "", "/C0 apod", "```", ""))
        result = check_documents(
            (doc(source),), config=Config(profile=ProfileConfig(name="generated-myst"))
        )

        assert [diagnostic.code for diagnostic in result.diagnostics] == ["GEN002"]
        span = result.diagnostics[0].span
        assert span is not None
        start = source.replace("\r\n", "\n").rindex("/C0 apod")
        assert (span.start, span.end, span.line, span.col, span.end_line, span.end_col) == (
            start,
            start + len("/C0 apod"),
            4,
            1,
            4,
            8,
        )


def test_suspicious_formula_facts_are_source_spanned_and_limited_to_explicit_math() -> None:
    source = (
        Path(__file__).parent / "fixtures" / "generated" / "suspicious_formula_text.md"
    ).read_text(encoding="utf-8")

    frontend_snapshot = MySTFrontend().lower((doc(source),))
    assert all(fact.kind == "candidate" for fact in frontend_snapshot.generated_formulas)
    snapshot = MathHost().classify(frontend_snapshot)

    assert [fact.kind for fact in snapshot.generated_formulas] == [
        "spaced-token",
        "garbled-marker",
        "spaced-token",
    ]
    assert [fact.text for fact in snapshot.generated_formulas] == [
        r"\A t t e n t",
        "/C0 apod",
        r"\A t t e n t",
    ]
    assert [
        source[fact.span.start : fact.span.end]
        for fact in snapshot.generated_formulas
        if fact.span is not None
    ] == [fact.text for fact in snapshot.generated_formulas]
    assert all(fact.source_math_fact_id is not None for fact in snapshot.generated_formulas)


def test_notebook_suspicious_formula_spans_use_splitline_positions() -> None:
    source = "$$\u2028\\A t t e n t { Q , K , V }\u2028/C0 apod\u2028$$\n"
    document = SourceDocument.from_text(
        PurePosixPath("generated.ipynb"),
        json.dumps(
            {
                "cells": [{"cell_type": "markdown", "metadata": {}, "source": source}],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        DocumentKind.NOTEBOOK,
    )

    snapshot = MathHost().classify(NotebookFrontend().lower((document,)))

    assert [fact.kind for fact in snapshot.generated_formulas] == [
        "spaced-token",
        "garbled-marker",
    ]
    assert [fact.span.cell_line for fact in snapshot.generated_formulas if fact.span] == [2, 3]
    assert [
        document.text[fact.span.start : fact.span.end]
        for fact in snapshot.generated_formulas
        if fact.span is not None
    ] == [json.dumps(fact.text)[1:-1] for fact in snapshot.generated_formulas]


def test_notebook_suspicious_formula_span_work_is_linear_in_match_count() -> None:
    fact_count = 128
    source = "$$" + "\u2028".join(r"\A t t e n t {Q}" for _ in range(fact_count)) + "$$\n"
    document = SourceDocument.from_text(
        PurePosixPath("generated-work.ipynb"),
        json.dumps(
            {
                "cells": [{"cell_type": "markdown", "metadata": {}, "source": source}],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        DocumentKind.NOTEBOOK,
    )
    frontend_snapshot = NotebookFrontend().lower((document,))
    [candidate] = frontend_snapshot.generated_formulas
    scanned_chars = 0

    class PrefixCountingText(str):
        def count(self, sub, start=0, end=None):
            nonlocal scanned_chars
            scanned_chars += (len(self) if end is None else end) - start
            if end is None:
                return super().count(sub, start)
            return super().count(sub, start, end)

    counted = replace(candidate, text=PrefixCountingText(candidate.text))
    snapshot = MathHost().classify(replace(frontend_snapshot, generated_formulas=(counted,)))

    assert len(snapshot.generated_formulas) == fact_count
    assert [fact.span.cell_line for fact in snapshot.generated_formulas if fact.span] == list(
        range(1, fact_count + 1)
    )
    assert scanned_chars <= 4 * len(counted.text) + 32


def test_generated_profile_emits_ordered_suspicious_formula_diagnostics_with_provenance() -> None:
    source = "$\\A t t e n t { Q , K , V }$ and $/C0 apod$.\n"
    generated = doc(
        source,
        origin=SourceOrigin(source_document_id="source/formulas.tex"),
    )

    result = check_documents(
        (generated,),
        config=Config(
            profile=ProfileConfig(
                name="generated-myst",
                source_kind="latex",
                conversion_stage="translation",
            ),
            scanner=ScannerConfig(inline_math=True),
        ),
    )
    diagnostics = tuple(
        diagnostic for diagnostic in result.diagnostics if diagnostic.code == "GEN002"
    )

    assert [
        (diagnostic.span.start, diagnostic.span.end)
        for diagnostic in diagnostics
        if diagnostic.span
    ] == [(1, 13), (34, 42)]
    assert [diagnostic.detail for diagnostic in diagnostics] == [
        r"spaced-token artifact: '\\A t t e n t'",
        "garbled-marker artifact: '/C0 apod'",
    ]
    assert all(diagnostic.profile == "generated-myst" for diagnostic in diagnostics)
    assert all(
        diagnostic.provenance_ids == ("generated.md::generated-provenance",)
        for diagnostic in diagnostics
    )
    assert [diagnostic.properties for diagnostic in diagnostics] == [
        (
            ("formula_artifact_kind", "spaced-token"),
            ("generated_document", "generated.md"),
            ("source_document", "source/formulas.tex"),
            ("source_kind", "latex"),
            ("conversion_stage", "translation"),
        ),
        (
            ("formula_artifact_kind", "garbled-marker"),
            ("generated_document", "generated.md"),
            ("source_document", "source/formulas.tex"),
            ("source_kind", "latex"),
            ("conversion_stage", "translation"),
        ),
    ]


def test_generated_formula_diagnostics_match_text_golden() -> None:
    generated = doc(
        "$\\A t t e n t { Q , K , V }$ and $/C0 apod$.\n",
        origin=SourceOrigin(source_document_id="source/formulas.tex"),
    )
    result = check_documents(
        (generated,),
        config=Config(
            profile=ProfileConfig(
                name="generated-myst",
                source_kind="latex",
                conversion_stage="translation",
            ),
            scanner=ScannerConfig(inline_math=True),
        ),
    )

    assert TextReporter().render(result) == (
        Path("tests/golden/text/generated_formula_text.txt").read_text(encoding="utf-8")
    )


def test_generated_formula_engine_keeps_provenance_as_ids_and_rule_properties() -> None:
    formula = GeneratedFormulaFact(
        fact_id="out/generated.md::formula::1",
        document_id="out/generated.md",
        span=None,
        raw=r"\A t t e n t {x}",
        confidence="inferred",
        kind="spaced-token",
        text=r"\A t t e n t {x}",
    )
    first = GeneratedProvenanceFact(
        fact_id="origin-a",
        document_id="out/generated.md",
        span=None,
        confidence="generated",
        generated_document_id="out/generated.md",
        source_document_id="source/a.xml",
        source_kind="jats-xml",
        conversion_stage="xml-to-markdown",
    )
    second = GeneratedProvenanceFact(
        fact_id="origin-b",
        document_id="out/generated.md",
        span=None,
        confidence="generated",
        generated_document_id="out/generated.md",
        source_document_id="source/b.tex",
        source_kind="latex",
        conversion_stage="translation",
    )

    diagnostics = GeneratedOutputEngine(profile="generated-myst").run(
        QueryHost(
            FactSnapshot(
                generated_provenance=(second, first),
                generated_formulas=(formula,),
            )
        )
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].provenance_ids == ("origin-a", "origin-b")
    assert diagnostics[0].properties == (("formula_artifact_kind", "spaced-token"),)


def test_generated_bracketed_diagnostic_uses_fact_delimiter_kind() -> None:
    cases = (
        (
            "literal",
            r"\[ x = y \]",
            "standalone [...] display delimiters are not portable generated Markdown",
        ),
        (
            "escaped",
            "[\nx = y\n]",
            r"standalone \[...\] display delimiters are not portable generated Markdown",
        ),
    )

    for delimiter_kind, text, expected_detail in cases:
        formula = GeneratedFormulaFact(
            fact_id="generated.md::formula::bracketed",
            document_id="generated.md",
            span=None,
            raw=text,
            confidence="source",
            kind="bracketed-block",
            text=text,
            complete=True,
            delimiter_kind=delimiter_kind,
        )
        [diagnostic] = GeneratedOutputEngine(profile="generated-myst").run(
            QueryHost(FactSnapshot(generated_formulas=(formula,)))
        )

        assert diagnostic.detail == expected_detail
        assert dict(diagnostic.properties)["delimiter_kind"] == delimiter_kind


def test_default_profile_and_valid_formula_text_keep_generated_diagnostic_branch_unchanged() -> (
    None
):
    source = "Valid $A(Q, K, V) = QK^T V$ and $a b c$.\n"

    trigger = "$/C0 apod$"
    default = check_documents(
        (doc(trigger),), config=Config(scanner=ScannerConfig(inline_math=True))
    )
    active = check_documents(
        (doc(trigger),),
        config=Config(
            profile=ProfileConfig(name="generated-myst"),
            scanner=ScannerConfig(inline_math=True),
        ),
    )
    generated = check_documents(
        (doc(source),),
        config=Config(
            profile=ProfileConfig(name="generated-myst"),
            scanner=ScannerConfig(inline_math=True),
        ),
    )

    assert default.diagnostics == ()
    assert [diagnostic.code for diagnostic in active.diagnostics] == ["GEN002"]
    assert active.diagnostics[0].span is not None
    assert trigger[active.diagnostics[0].span.start : active.diagnostics[0].span.end] == (
        "/C0 apod"
    )
    assert all(diagnostic.code != "GEN002" for diagnostic in generated.diagnostics)


def test_math_host_classification_is_idempotent_for_final_generated_facts() -> None:
    first = MathHost().classify(MySTFrontend().lower((doc(r"$/C0 apod$"),)))

    assert [fact.kind for fact in first.generated_formulas] == ["garbled-marker"]
    assert MathHost().classify(first).generated_formulas == first.generated_formulas


def test_suspicious_formula_classifier_keeps_valid_spaced_math_quiet() -> None:
    cases = (
        ("$A B C D E (x)$", False),
        ("$A B C D (Q, K, V)$", False),
        ("$A b c d e (x)$", False),
        ("$A b c d e f(x)$", False),
        ("$a b c d e f(x)$", False),
        ("$A t t e (x)$", False),
        ("$A t t e n (x)$", False),
        ("$a b c d e (x)$", False),
        ("$a b c d (x, y, z)$", False),
        ("$A t t e n t (Q, K, V)$", True),
        (r"$A B C D E \times (x)$", False),
        ("$A t t E n t (x)$", False),
        ("$A t t e n t (x)$", False),
        ("$/C0 apodx$", False),
        ("$/C0 apod$", True),
        ("$A t, B t t e n t (Q, K, V)$", True),
        ("$word B t t e n t (Q, K, V)$", True),
    )

    for source, suspicious in cases:
        snapshot = MathHost().classify(MySTFrontend().lower((doc(source),)))

        assert bool(snapshot.generated_formulas) is suspicious, source
        if suspicious:
            assert snapshot.generated_formulas[0].kind in {"spaced-token", "garbled-marker"}


def test_suspicious_formula_classifier_flags_spaced_commands() -> None:
    snapshot = MathHost().classify(MySTFrontend().lower((doc(r"$\A t t e n t {x}$"),)))

    assert [(fact.kind, fact.text) for fact in snapshot.generated_formulas] == [
        ("spaced-token", r"\A t t e n t")
    ]


def test_suspicious_formula_classifier_respects_command_escape_parity() -> None:
    even = "\\" * 2
    source = "$" + even + r"A t t e n t {x}$ and $\A t t e n t {x}$"

    snapshot = MathHost().classify(MySTFrontend().lower((doc(source),)))

    assert [fact.text for fact in snapshot.generated_formulas] == [r"\A t t e n t"]
    [fact] = snapshot.generated_formulas
    assert fact.span is not None
    assert source[fact.span.start : fact.span.end] == fact.text


def test_suspicious_formula_classifier_ignores_active_tex_comments() -> None:
    snapshot = MathHost().classify(MySTFrontend().lower((doc(r"$x % \A t t e n t {x}$"),)))

    assert snapshot.generated_formulas == ()


def test_generated_formula_fact_rejects_mixed_candidate_and_final_states() -> None:
    frontend = MySTFrontend().lower((doc("$/C0 apod$"),))
    candidate = frontend.generated_formulas[0]
    assert candidate.kind == "candidate"
    assert candidate.candidate_kind == "formula-text"

    with pytest.raises(ValueError, match="candidate_kind"):
        replace(candidate, kind="garbled-marker")

    final = MathHost().classify(frontend).generated_formulas[0]
    assert final.kind == "garbled-marker"
    assert final.candidate_kind is None

    with pytest.raises(ValueError, match="candidate_kind"):
        replace(final, kind="candidate")


def test_generated_formula_fact_requires_bracketed_completeness_metadata() -> None:
    candidate = MySTFrontend().lower((doc("\\[x = y\\]"),)).generated_formulas[0]

    assert candidate.candidate_kind == "bracketed-block"
    assert candidate.delimiter_kind == "escaped"
    with pytest.raises(ValueError, match="completeness metadata"):
        replace(candidate, complete=None)

    with pytest.raises(ValueError, match="delimiter kind"):
        replace(candidate, delimiter_kind=None)

    final = MathHost().classify(MySTFrontend().lower((doc("[\nx = y\n]\n"),))).generated_formulas[0]
    assert final.kind == "bracketed-block"
    assert final.delimiter_kind == "literal"
    with pytest.raises(ValueError, match="delimiter kind"):
        replace(final, delimiter_kind=None)

    suspicious = GeneratedFormulaFact(
        fact_id="generated.md::formula::suspicious",
        document_id="generated.md",
        span=None,
        raw="/C0 apod",
        confidence="inferred",
        kind="garbled-marker",
        text="/C0 apod",
    )
    with pytest.raises(ValueError, match="delimiter kind"):
        replace(suspicious, delimiter_kind="literal")


def test_generated_formula_fact_rejects_missing_placeholder_and_spurious_completion() -> None:
    placeholder = MySTFrontend().lower((doc("formula-not-decoded\n"),)).generated_formulas[0]

    with pytest.raises(ValueError, match="placeholder_kind"):
        replace(placeholder, placeholder_kind=None)

    formula = MySTFrontend().lower((doc("$x$"),)).generated_formulas[0]
    assert formula.candidate_kind == "formula-text"
    with pytest.raises(ValueError, match="complete"):
        replace(formula, complete=True)


@pytest.mark.parametrize(
    ("kind", "candidate_kind", "placeholder_kind", "complete"),
    [
        ("candidate", "placeholder", "empty-display-math", True),
        ("empty-display", None, "empty-display-math", True),
        ("candidate", "bracketed-block", None, False),
        ("candidate", "bracketed-block", None, True),
        ("bracketed-block", None, None, False),
        ("bracketed-block", None, None, True),
    ],
)
def test_generated_formula_fact_accepts_completion_states(
    kind: str,
    candidate_kind: str | None,
    placeholder_kind: str | None,
    complete: bool,
) -> None:
    candidate = MySTFrontend().lower((doc("formula-not-decoded\n"),)).generated_formulas[0]

    fact = replace(
        candidate,
        kind=kind,
        candidate_kind=candidate_kind,
        placeholder_kind=placeholder_kind,
        complete=complete,
        delimiter_kind=(
            "escaped" if kind == "bracketed-block" or candidate_kind == "bracketed-block" else None
        ),
    )

    assert fact.kind == kind
    assert fact.complete is complete


@pytest.mark.parametrize(
    ("kind", "candidate_kind"),
    [("candidate", "placeholder"), ("empty-display", None)],
)
def test_generated_formula_fact_rejects_incomplete_empty_display(
    kind: str, candidate_kind: str | None
) -> None:
    candidate = MySTFrontend().lower((doc("formula-not-decoded\n"),)).generated_formulas[0]

    with pytest.raises(ValueError, match="complete=True"):
        replace(
            candidate,
            kind=kind,
            candidate_kind=candidate_kind,
            placeholder_kind="empty-display-math",
            complete=False,
        )


@pytest.mark.parametrize(
    ("placeholder_kind", "complete"),
    [
        ("formula-not-decoded", None),
        ("empty-display-math", True),
        ("formula-image", None),
    ],
)
def test_candidate_placeholder_facts_allow_each_placeholder_kind(
    placeholder_kind: str, complete: bool | None
) -> None:
    candidate = MySTFrontend().lower((doc("formula-not-decoded\n"),)).generated_formulas[0]

    fact = replace(
        candidate,
        placeholder_kind=placeholder_kind,
        complete=complete,
    )

    assert fact.kind == "candidate"
    assert fact.candidate_kind == "placeholder"
    assert fact.placeholder_kind == placeholder_kind


@pytest.mark.parametrize(
    ("kind", "expected_placeholder_kind", "wrong_placeholder_kind"),
    [
        ("placeholder", "formula-not-decoded", "formula-image"),
        ("empty-display", "empty-display-math", "formula-not-decoded"),
        ("image-placeholder", "formula-image", "empty-display-math"),
    ],
)
def test_final_placeholder_facts_reject_contradictory_placeholder_kind(
    kind: str, expected_placeholder_kind: str, wrong_placeholder_kind: str
) -> None:
    candidate = MySTFrontend().lower((doc("formula-not-decoded\n"),)).generated_formulas[0]
    final = replace(
        candidate,
        kind=kind,
        candidate_kind=None,
        placeholder_kind=expected_placeholder_kind,
        complete=True if kind == "empty-display" else None,
    )

    assert final.kind == kind
    with pytest.raises(ValueError, match="requires placeholder_kind"):
        replace(final, placeholder_kind=wrong_placeholder_kind)


def test_notebook_source_list_generated_subspans_preserve_exact_segments() -> None:
    payload = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [r"Use $\A t", " t e n t {Q}$.\r\n"],
            }
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    document = SourceDocument.from_text(
        PurePosixPath("generated-segments.ipynb"),
        json.dumps(payload, sort_keys=True),
        DocumentKind.NOTEBOOK,
    )

    frontend_snapshot = NotebookFrontend().lower((document,))
    snapshot = MathHost().classify(frontend_snapshot)

    [fact] = snapshot.generated_formulas
    assert fact.kind == "spaced-token"
    assert fact.text == r"\A t t e n t"
    assert fact.span is not None
    assert fact.span.cell == 0
    assert fact.span.cell_line == 1
    assert len(fact.span.segments) == len(fact.text)
    assert (
        "".join(
            json.loads(f'"{document.text[start:end]}"')
            for segment in fact.span.segments
            for start, end in segment.ranges
        )
        == fact.text
    )

    [candidate] = frontend_snapshot.generated_formulas
    assert candidate.span is not None
    malformed = replace(
        candidate,
        span=replace(candidate.span, segments=candidate.span.segments[:-1]),
    )
    with pytest.raises(ValueError, match="generated formula source mapping does not match"):
        MathHost().classify(replace(frontend_snapshot, generated_formulas=(malformed,)))


def test_suspicious_formula_facts_are_deterministic_after_newline_normalization() -> None:
    lf = MathHost().classify(MySTFrontend().lower((doc("$\\A t t e n t { Q }$\n"),)))
    crlf = MathHost().classify(MySTFrontend().lower((doc("$\\A t t e n t { Q }$\r\n"),)))

    assert lf.generated_formulas == crlf.generated_formulas


def test_generated_formula_diagnostic_does_not_require_provenance() -> None:
    result = check_documents(
        (doc("Suspicious $/C0 apod$.\n"),),
        config=Config(
            profile=ProfileConfig(name="generated-myst"),
            scanner=ScannerConfig(inline_math=True),
        ),
    )

    diagnostics = tuple(
        diagnostic for diagnostic in result.diagnostics if diagnostic.code == "GEN002"
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].provenance_ids == ()
    assert dict(diagnostics[0].properties) == {"formula_artifact_kind": "garbled-marker"}
