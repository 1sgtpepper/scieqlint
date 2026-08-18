from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.api import check_documents
from scieqlint.config.model import AlgebraConfig, ChecksConfig, Config
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("aligned.md"),
        text,
        DocumentKind.MARKDOWN,
    )


def without_algebra() -> Config:
    return Config(checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)))


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

    snapshot = MySTFrontend().lower((doc(source),))
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

    snapshot = MySTFrontend().lower((document,))
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


def test_duplicate_aligned_labels_make_refs_ambiguous_without_duplicate_public_reports() -> None:
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

    snapshot = MySTFrontend().lower((document,))
    query = QueryHost(snapshot)
    engine = ReferenceEngine().run(query)
    result = check_documents([document], config=without_algebra())

    assert query.references.duplicate_equation_targets() == {"dup": snapshot.equation_labels}
    assert [(diagnostic.code, diagnostic.message) for diagnostic in engine] == [
        ("REF001", "duplicate equation label: dup")
    ]
    assert [diagnostic.code for diagnostic in result.diagnostics].count("REF001") == 1


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

    snapshot = MySTFrontend().lower((doc(source),))

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

    snapshot = MySTFrontend().lower((doc(source),))

    assert snapshot.display_math[0].container == "dollar-dollar"
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-ref", "valid")
    ]


def test_incomplete_aligned_environment_keeps_display_identity_without_ams_claim() -> None:
    source = """\
$$
\\begin{align}
x &= \\eqref{missing}
$$
"""

    snapshot = MySTFrontend().lower((doc(source),))

    assert [fact.container for fact in snapshot.display_math] == ["dollar-dollar"]
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-eqref", "missing")
    ]
