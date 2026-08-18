from __future__ import annotations

from pathlib import Path, PurePosixPath

from scieqlint.app import check_documents
from scieqlint.config.model import Config, ProfileConfig
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument, SourceOrigin
from scieqlint.parse.math import MathHost


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


def test_suspicious_formula_facts_are_deterministic_after_newline_normalization() -> None:
    lf = MathHost().classify(MySTFrontend().lower((doc("$A t t e n t ( Q )$\n"),)))
    crlf = MathHost().classify(MySTFrontend().lower((doc("$A t t e n t ( Q )$\r\n"),)))

    assert lf.generated_formulas == crlf.generated_formulas
