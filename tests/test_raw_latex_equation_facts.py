from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from scieqlint.engine.reference import ReferenceEngine
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.parse.math import MathHost
from scieqlint.query.host import QueryHost


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("raw-equations.md"),
        text,
        DocumentKind.MARKDOWN,
    )


def lower(document: SourceDocument):
    return MathHost().classify(MySTFrontend().lower((document,)))


def test_raw_equation_environment_preserves_label_and_adjacent_reference_facts() -> None:
    source = r"""\begin{equation}
E = mc^2
\label{eq:energy}
\end{equation}

{eq}`eq:energy`
"""

    snapshot = lower(doc(source))

    assert [(fact.container, fact.body) for fact in snapshot.display_math] == [
        ("ams", "E = mc^2\n\\label{eq:energy}")
    ]
    assert [(fact.label, fact.source_block_id) for fact in snapshot.equation_labels] == [
        ("eq:energy", snapshot.display_math[0].fact_id)
    ]
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("eq", "eq:energy")
    ]
    assert snapshot.unknown_math == ()
    assert ReferenceEngine().run(QueryHost(snapshot)) == ()
    assert snapshot.display_math[0].span is not None
    assert (
        source[snapshot.display_math[0].span.start : snapshot.display_math[0].span.end]
        == source[: source.index("\n\n")]
    )


def test_raw_align_environment_preserves_internal_tex_reference_and_exact_span() -> None:
    source = r"""\begin{align}
a &= b \label{known} \\
c &= d \eqref{missing}
\end{align}
"""

    snapshot = lower(doc(source))
    diagnostics = ReferenceEngine().run(QueryHost(snapshot))

    assert [(fact.label, fact.label_syntax_kind) for fact in snapshot.equation_labels] == [
        ("known", "tex-label")
    ]
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-eqref", "missing")
    ]
    assert [(diagnostic.code, diagnostic.detail) for diagnostic in diagnostics] == [
        ("REF002", r"reference text: \eqref{missing}")
    ]
    span = snapshot.equation_refs[0].target_span
    assert span is not None
    assert source[span.start : span.end] == "missing"


def test_escaped_raw_equation_markers_and_empty_targets_are_not_facts() -> None:
    source = r"""\begin{equation}
x = y \\label{escaped} \\ref{escaped} \ref{ }
\end{equation}
"""

    snapshot = lower(doc(source))

    assert snapshot.equation_labels == ()
    assert snapshot.equation_refs == ()
    assert snapshot.unknown_math == ()


def test_unsupported_raw_math_environment_is_unknown_without_losing_refs_or_labels() -> None:
    source = r"""\begin{cases}
x & \text{if } y \label{piecewise}
\ref{outside}
\end{cases}
"""

    snapshot = lower(doc(source))

    assert len(snapshot.display_math) == 1
    assert [(fact.label, fact.source_block_id) for fact in snapshot.equation_labels] == [
        ("piecewise", snapshot.display_math[0].fact_id)
    ]
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-ref", "outside")
    ]
    assert [
        (fact.source_math_fact_id, fact.reason, fact.excerpt) for fact in snapshot.unknown_math
    ] == [(snapshot.display_math[0].fact_id, "environment", "cases")]


@pytest.mark.parametrize("environment", ["figure", "table", "itemize", "document"])
def test_nonmath_raw_environments_are_not_equation_candidates(environment: str) -> None:
    source = rf"""\begin{{{environment}}}
\label{{not-an-equation}}
\ref{{missing}}
\end{{{environment}}}
"""

    snapshot = lower(doc(source))

    assert snapshot.display_math == ()
    assert snapshot.equation_labels == ()
    assert snapshot.equation_refs == ()
    assert snapshot.unknown_math == ()
    assert snapshot.generated_formulas == ()


def test_nonmath_raw_label_does_not_collide_with_an_equation_label() -> None:
    source = r"""\begin{figure}
\label{shared}
\end{figure}

\begin{equation}
x = 1 \label{shared}
\end{equation}

{eq}`shared`
"""

    snapshot = lower(doc(source))
    diagnostics = ReferenceEngine().run(QueryHost(snapshot))

    assert [label.label for label in snapshot.equation_labels] == ["shared"]
    assert [diagnostic.code for diagnostic in diagnostics] == []


def test_nested_aligned_environment_remains_owned_by_supported_outer_equation() -> None:
    source = r"""\begin{equation}
\begin{aligned}
a &= b \\
c &= d
\end{aligned}
\label{nested}
\end{equation}
"""

    snapshot = lower(doc(source))

    assert len(snapshot.display_math) == 1
    assert [fact.label for fact in snapshot.equation_labels] == ["nested"]
    assert snapshot.unknown_math == ()


def test_raw_environment_scanning_respects_code_and_existing_math_ownership() -> None:
    source = r"""```tex
\begin{equation}
\label{code-only}
\end{equation}
```

$$
\begin{align}
x &= y \label{dollar-owned}
\end{align}
$$

\begin{equation}
z = 1 \label{raw-owned}
\end{equation}
"""

    snapshot = lower(doc(source))

    assert [fact.label for fact in snapshot.equation_labels] == [
        "dollar-owned",
        "raw-owned",
    ]
    assert len(snapshot.display_math) == 2
    assert [fact.container for fact in snapshot.display_math] == ["ams", "ams"]
    assert all("code-only" not in (fact.raw or "") for fact in snapshot.display_math)


def test_unclosed_raw_environment_owns_to_eof_and_preserves_partial_facts() -> None:
    source = r"""Before.

\begin{equation}
x = y \label{partial}
\eqref{missing}
"""

    snapshot = lower(doc(source))

    assert len(snapshot.display_math) == 1
    assert snapshot.display_math[0].span is not None
    assert snapshot.display_math[0].span.end == len(source)
    assert [fact.label for fact in snapshot.equation_labels] == ["partial"]
    assert [fact.target for fact in snapshot.equation_refs] == ["missing"]
    assert [(fact.reason, fact.excerpt) for fact in snapshot.unknown_math] == [
        ("parse_limit", "equation")
    ]


def test_unmatched_raw_environment_closer_is_ignored_before_a_valid_environment() -> None:
    source = r"""\end{equation}

\begin{equation}
x = y
\end{equation}
"""

    snapshot = lower(doc(source))

    assert [(fact.container, fact.body) for fact in snapshot.display_math] == [("ams", "x = y")]
    assert snapshot.unknown_math == ()


def test_raw_equation_facts_are_deterministic_after_newline_normalization() -> None:
    lf = lower(doc("\\begin{equation}\nx=1\\label{x}\n\\end{equation}\n"))
    crlf = lower(doc("\\begin{equation}\r\nx=1\\label{x}\r\n\\end{equation}\r\n"))

    assert lf.display_math == crlf.display_math
    assert lf.equation_labels == crlf.equation_labels
    assert lf.equation_refs == crlf.equation_refs
    assert lf.unknown_math == crlf.unknown_math
