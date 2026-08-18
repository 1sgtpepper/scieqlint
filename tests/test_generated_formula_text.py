from __future__ import annotations

from pathlib import Path, PurePosixPath

from scieqlint.app import check_documents
from scieqlint.config.model import Config, ProfileConfig
from scieqlint.engine.generated import GeneratedOutputEngine
from scieqlint.facts.generated import GeneratedFormulaFact, GeneratedProvenanceFact
from scieqlint.facts.math import InlineMathFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.generated import scan_formula_candidates
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument, SourceOrigin
from scieqlint.parse.math import MathHost
from scieqlint.query.host import QueryHost
from scieqlint.report.text import TextReporter
from scieqlint.source.maps import SourceMap


def doc(text: str, *, origin: SourceOrigin | None = None) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("generated.md"),
        text,
        DocumentKind.MARKDOWN,
        origin=origin,
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
        "A t t e n t ( Q , K , V )",
        "/C0 apod",
        "A t t e n t ( Q )",
    ]
    assert [
        source[fact.span.start : fact.span.end]
        for fact in snapshot.generated_formulas
        if fact.span is not None
    ] == [fact.text for fact in snapshot.generated_formulas]
    assert all(fact.source_math_fact_id is not None for fact in snapshot.generated_formulas)


def test_generated_profile_emits_ordered_suspicious_formula_diagnostics_with_provenance() -> None:
    source = "$A t t e n t ( Q , K , V )$ and $/C0 apod$.\n"
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
            )
        ),
    )
    diagnostics = tuple(
        diagnostic for diagnostic in result.diagnostics if diagnostic.code == "GEN002"
    )

    assert [diagnostic.detail for diagnostic in diagnostics] == [
        "spaced-token artifact: 'A t t e n t ( Q , K , V )'",
        "garbled-marker artifact: '/C0 apod'",
    ]
    assert [
        (diagnostic.span.start, diagnostic.span.end)
        for diagnostic in diagnostics
        if diagnostic.span
    ] == [
        (1, 26),
        (33, 41),
    ]
    assert all(diagnostic.profile == "generated-myst" for diagnostic in diagnostics)
    assert all(
        diagnostic.provenance_ids == ("generated.md::generated-provenance",)
        for diagnostic in diagnostics
    )
    assert [dict(diagnostic.properties) for diagnostic in diagnostics] == [
        {
            "formula_artifact_kind": "spaced-token",
            "generated_document": "generated.md",
            "source_document": "source/formulas.tex",
            "source_kind": "latex",
            "conversion_stage": "translation",
        },
        {
            "formula_artifact_kind": "garbled-marker",
            "generated_document": "generated.md",
            "source_document": "source/formulas.tex",
            "source_kind": "latex",
            "conversion_stage": "translation",
        },
    ]


def test_generated_formula_diagnostics_match_text_golden() -> None:
    generated = doc(
        "$A t t e n t ( Q , K , V )$ and $/C0 apod$.\n",
        origin=SourceOrigin(source_document_id="source/formulas.tex"),
    )
    result = check_documents(
        (generated,),
        config=Config(
            profile=ProfileConfig(
                name="generated-myst",
                source_kind="latex",
                conversion_stage="translation",
            )
        ),
    )

    assert TextReporter().render(result) == (
        Path("tests/golden/text/generated_formula_text.txt").read_text(encoding="utf-8")
    )


def test_generated_formula_diagnostic_projects_all_provenance_metadata() -> None:
    formula = GeneratedFormulaFact(
        fact_id="out/generated.md::formula::1",
        document_id="out/generated.md",
        span=None,
        raw="A t t e n t (x)",
        confidence="inferred",
        kind="spaced-token",
        text="A t t e n t (x)",
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
    assert dict(diagnostics[0].properties) == {
        "formula_artifact_kind": "spaced-token",
        "provenance_1_conversion_stage": "xml-to-markdown",
        "provenance_1_generated_document": "out/generated.md",
        "provenance_1_source_document": "source/a.xml",
        "provenance_1_source_kind": "jats-xml",
        "provenance_2_conversion_stage": "translation",
        "provenance_2_generated_document": "out/generated.md",
        "provenance_2_source_document": "source/b.tex",
        "provenance_2_source_kind": "latex",
    }


def test_default_profile_and_valid_formula_text_keep_generated_diagnostic_branch_unchanged() -> (
    None
):
    source = "Valid $A(Q, K, V) = QK^T V$ and $a b c$.\n"

    default = check_documents((doc("$A t t e n t ( Q )$.\n"),), config=Config())
    generated = check_documents(
        (doc(source),),
        config=Config(profile=ProfileConfig(name="generated-myst")),
    )

    assert all(diagnostic.code != "GEN002" for diagnostic in default.diagnostics)
    assert all(diagnostic.code != "GEN002" for diagnostic in generated.diagnostics)


def test_suspicious_formula_classifier_keeps_valid_spaced_math_quiet() -> None:
    cases = (
        ("$A B C D E (x)$", False),
        ("$a b c d e f(x)$", False),
        ("$A t t e (x)$", False),
        ("$A t t e n (x)$", True),
        ("$a b c d e (x)$", False),
        (r"$A B C D E \times (x)$", False),
        ("$A t t E n t (x)$", False),
        ("$A t t e n t (x)$", True),
        ("$/C0 apodx$", False),
        ("$/C0 apod$", True),
    )

    for source, suspicious in cases:
        snapshot = MathHost().classify(MySTFrontend().lower((doc(source),)))

        assert bool(snapshot.generated_formulas) is suspicious, source
        if suspicious:
            assert snapshot.generated_formulas[0].kind in {"spaced-token", "garbled-marker"}


def test_suspicious_formula_classifier_deduplicates_overlapping_artifacts() -> None:
    snapshot = MathHost().classify(MySTFrontend().lower((doc("$A t t e n t ( /C0 apod )$"),)))

    assert [(fact.kind, fact.text) for fact in snapshot.generated_formulas] == [
        ("spaced-token", "A t t e n t ( /C0 apod )")
    ]


def test_suspicious_formula_classifier_flags_spaced_commands() -> None:
    snapshot = MathHost().classify(MySTFrontend().lower((doc(r"$\A t t e n t {x}$"),)))

    assert [(fact.kind, fact.text) for fact in snapshot.generated_formulas] == [
        ("spaced-token", r"\A t t e n t")
    ]


def test_formula_candidate_scan_skips_foreign_and_unspanned_math() -> None:
    document = doc("$x$")
    foreign = InlineMathFact(
        fact_id="foreign",
        document_id="other.md",
        span=SourceMap.for_document(document).span(0, 3),
        raw="$x$",
        confidence="source",
        body="x",
        delimiter_kind="dollar",
        context="paragraph",
    )
    unspanned = InlineMathFact(
        fact_id="unspanned",
        document_id=document.path.as_posix(),
        span=None,
        raw="$x$",
        confidence="source",
        body="x",
        delimiter_kind="dollar",
        context="paragraph",
    )

    assert scan_formula_candidates(document, (foreign, unspanned), ()) == ()


def test_math_host_keeps_existing_facts_and_skips_unmappable_candidates() -> None:
    document = doc("plain text")
    existing = GeneratedFormulaFact(
        fact_id="existing",
        document_id=document.path.as_posix(),
        span=None,
        raw="existing",
        confidence="inferred",
        kind="garbled-marker",
        text="existing",
    )
    foreign_candidate = GeneratedFormulaFact(
        fact_id="foreign-candidate",
        document_id="other.md",
        span=None,
        raw="candidate",
        confidence="source",
        kind="candidate",
        text="candidate",
    )
    unspanned_candidate = GeneratedFormulaFact(
        fact_id="unspanned-candidate",
        document_id=document.path.as_posix(),
        span=None,
        raw="candidate",
        confidence="source",
        kind="candidate",
        text="candidate",
    )

    snapshot = MathHost().classify(
        FactSnapshot(
            documents=(document,),
            generated_formulas=(existing, foreign_candidate, unspanned_candidate),
        )
    )

    assert snapshot.generated_formulas == (existing,)


def test_suspicious_formula_facts_are_deterministic_after_newline_normalization() -> None:
    lf = MathHost().classify(MySTFrontend().lower((doc("$A t t e n t ( Q )$\n"),)))
    crlf = MathHost().classify(MySTFrontend().lower((doc("$A t t e n t ( Q )$\r\n"),)))

    assert lf.generated_formulas == crlf.generated_formulas
