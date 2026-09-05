from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from scieqlint.api import check_documents, graph_documents
from scieqlint.config.model import ChecksConfig, Config, ReferencesConfig, ScannerConfig
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


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("quote", ["quoted", "`quoted'"])
def test_tex_quote_keeps_later_equation_target_visible(quote: str, newline: str) -> None:
    source = (
        "\\begin{equation}\nx = \\text{" + quote + "}\n\\end{equation}\n\n"
        "A normal `code` example.\n\n$$\ny = y\n$$ {#eq:second}\n"
    )
    reference_text = "See {eq}`eq:second` and {eq}`absent`.\n"
    reference = SourceDocument.from_text(
        PurePosixPath("reference.md"), reference_text, DocumentKind.MARKDOWN
    )

    result = check_documents((doc(source.replace("\n", newline)), reference), config=Config())

    assert result.files_checked == 2
    assert result.math_blocks_checked == 1
    assert [item.code for item in result.diagnostics] == ["REF002"]
    span = result.diagnostics[0].span
    assert span is not None
    assert span.path == reference.path
    start = reference_text.index("absent")
    assert (span.start, span.end) == (start, start + len("absent"))


@pytest.mark.parametrize(
    "body",
    [
        "x = \\text{`quoted'}\n",
        "\\begin{aligned}\nx &= \\text{`quoted'}\n\\end{aligned}\n",
        "\\begin{verbatim}\n`quoted'\n\\end{verbatim}\n",
        "% `quoted'\nx = x\n",
    ],
)
def test_quote_range_cannot_reclaim_source_after_raw_closer(body: str) -> None:
    first = "\\begin{equation}\n" + body + "\\end{equation}"
    second = "\\begin{equation}\ny = y \\label{second}\n\\end{equation}"
    source = first + "\n\n" + second + "\n\nA trailing `code` example.\n"

    snapshot = lower(doc(source))

    assert [(fact.environment, fact.complete) for fact in snapshot.display_math] == [
        ("equation", True),
        ("equation", True),
    ]
    assert [fact.raw for fact in snapshot.display_math] == [first, second]
    assert [fact.label for fact in snapshot.equation_labels] == ["second"]


@pytest.mark.parametrize("literal", ["%", r"\begin{verbatim}", r"\begin{equation}"])
def test_markdown_code_opened_first_keeps_tex_controls_literal(literal: str) -> None:
    source = "`" + literal + "` \\begin{equation}\nx = x \\label{live}\n\\end{equation}\n"

    snapshot = lower(doc(source))

    assert [(fact.environment, fact.complete) for fact in snapshot.display_math] == [
        ("equation", True)
    ]
    assert [fact.label for fact in snapshot.equation_labels] == ["live"]


@pytest.mark.parametrize("environment", ["verbatim", "verbatim*"])
@pytest.mark.parametrize("literal", ["$$", "```math"])
@pytest.mark.parametrize("outside", ["", "$$", "```math"])
def test_raw_verbatim_delimiters_do_not_consume_outside_math(
    environment: str, literal: str, outside: str
) -> None:
    prefix = f"\\begin{{{environment}}}\n{literal}\n\\end{{{environment}}}\n\n"
    source = prefix + outside + "\n"

    result = check_documents((doc(source),), config=Config())

    assert result.math_blocks_checked == 0
    assert [
        (item.code, item.span.start, item.span.end)
        for item in result.diagnostics
        if item.span is not None
    ] == ([("SCAN001", len(prefix), len(prefix) + len(outside))] if outside else [])
    assert len(result.diagnostics) == bool(outside)


@pytest.mark.parametrize("literal", ["$$", "```math"])
def test_raw_verbatim_keeps_outside_equation_and_reference_consumers_active(literal: str) -> None:
    source = (
        f"\\begin{{verbatim}}\n{literal}\n\\end{{verbatim}}\n\n"
        "$$\nx = 1 \\label{live}\n$$\nSee {eq}`live` and {eq}`absent`.\n"
    )
    document = doc(source)

    result = check_documents((document,), config=Config())
    graph = graph_documents((document,), config=Config())

    assert result.math_blocks_checked == 1
    assert [item.code for item in result.diagnostics] == ["REF002"]
    assert result.diagnostics[0].span is not None
    assert source[result.diagnostics[0].span.start : result.diagnostics[0].span.end] == "absent"
    assert [(node.kind, node.label) for node in graph.nodes] == [
        ("equation", "live"),
        ("reference", "live"),
        ("reference", "absent"),
    ]


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
    assert snapshot.display_math[0].source_syntax == "raw-latex"
    assert [(fact.label, fact.source_block_id) for fact in snapshot.equation_labels] == [
        ("eq:energy", snapshot.display_math[0].fact_id)
    ]
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("eq", "eq:energy")
    ]
    assert snapshot.unknown_math == ()
    assert ReferenceEngine().run(QueryHost(snapshot)) == ()
    assert check_documents((doc(source),), config=Config()).diagnostics == ()
    assert snapshot.display_math[0].span is not None
    assert (
        source[snapshot.display_math[0].span.start : snapshot.display_math[0].span.end]
        == source[: source.index("\n\n")]
    )


def test_public_strict_reference_check_requires_a_raw_equation_label() -> None:
    source = "\\begin{equation}\nx = 1\n\\end{equation}\n"
    config = Config(checks=ChecksConfig(references=ReferencesConfig(missing_label_strict=True)))

    result = check_documents((doc(source),), config=config)

    assert [(diagnostic.code, diagnostic.equation) for diagnostic in result.diagnostics] == [
        ("REF003", "x = 1")
    ]


@pytest.mark.parametrize(
    "source",
    [
        "\\begin{equation}\nx = 1\n",
        "\\begin{mystery}\nx = 1\n\\end{mystery}\n",
    ],
)
def test_public_strict_reference_check_ignores_unaccepted_raw_candidates(source: str) -> None:
    config = Config(checks=ChecksConfig(references=ReferencesConfig(missing_label_strict=True)))

    result = check_documents((doc(source),), config=config)

    assert all(diagnostic.code != "REF003" for diagnostic in result.diagnostics)


def test_graph_exports_raw_equation_labels_and_internal_references() -> None:
    source = "\\begin{equation}\nx = 1 \\label{live} \\eqref{live}\n\\end{equation}\n"

    graph = graph_documents((doc(source),), config=Config())

    equation_nodes = [node for node in graph.nodes if node.kind == "equation"]
    reference_nodes = [node for node in graph.nodes if node.kind == "reference"]
    assert [(node.label, node.source) for node in equation_nodes] == [("live", "latex_label")]
    assert [(node.label, node.source) for node in reference_nodes] == [("live", "latex_eqref")]
    assert [(edge.target, edge.target_label, edge.raw) for edge in graph.edges] == [
        (equation_nodes[0].id, "live", "\\eqref{live}")
    ]


def test_graph_does_not_extract_raw_facts_when_markdown_scanning_is_disabled() -> None:
    source = r"""\begin{equation}
x = 1 \label{disabled}
\end{equation}
"""

    graph = graph_documents(
        (doc(source),),
        config=Config(scanner=ScannerConfig(markdown=False)),
    )

    assert graph.nodes == ()
    assert graph.edges == ()


def test_raw_owner_hides_later_markdown_and_myst_reference_tokens() -> None:
    source = r"""\begin{equation}
[inside](#inside) {eq}`inside`
\end{equation}
"""

    snapshot = lower(doc(source))

    assert snapshot.generic_refs == ()
    assert snapshot.equation_refs == ()


@pytest.mark.public_regression
def test_public_check_and_graph_hide_legacy_refs_inside_raw_candidates() -> None:
    source = r"""\begin{figure}
[figure-hidden](#figure-hidden)
\end{figure}

\begin{mystery}
[mystery-hidden](#mystery-hidden)
\end{mystery}

\begin{equation}
[equation-hidden](#equation-hidden) {eq}`equation-hidden`
\eqref{missing}
\end{equation}

See [outside](#outside-missing).
"""
    document = doc(source)

    result = check_documents((document,), config=Config())
    missing_start = source.index("missing")
    outside_start = source.index("outside-missing")
    assert result.files_checked == 1
    assert result.math_blocks_checked == 0
    assert [
        (
            diagnostic.code,
            diagnostic.detail,
            diagnostic.span.start if diagnostic.span is not None else None,
            diagnostic.span.end if diagnostic.span is not None else None,
        )
        for diagnostic in result.diagnostics
    ] == [
        ("REF002", r"reference text: \eqref{missing}", missing_start, missing_start + 7),
        (
            "REF002",
            "reference text: [outside](#outside-missing)",
            outside_start,
            outside_start + len("outside-missing"),
        ),
    ]
    assert result.exit_code() == 0

    graph = graph_documents((document,), config=Config())
    assert graph.schema_version == "0.3"
    assert [(node.kind, node.label, node.source) for node in graph.nodes] == [
        ("reference", "missing", "latex_eqref"),
        ("reference", "outside-missing", "markdown_anchor"),
    ]
    assert [(edge.target_label, edge.raw, edge.source_kind) for edge in graph.edges] == [
        ("missing", r"\eqref{missing}", "latex_eqref"),
        ("outside-missing", "[outside](#outside-missing)", "markdown_anchor"),
    ]


@pytest.mark.public_regression
def test_public_opaque_markdown_verbatim_marker_does_not_hide_raw_equation() -> None:
    source = "`\\begin{verbatim}`\n\n\\begin{equation}\nx = 1 \\eqref{missing}\n\\end{equation}\n"
    document = doc(source)

    result = check_documents((document,), config=Config())
    target_start = source.index("missing")
    assert result.files_checked == 1
    assert result.math_blocks_checked == 0
    assert [
        (
            diagnostic.code,
            diagnostic.detail,
            diagnostic.span.start if diagnostic.span is not None else None,
            diagnostic.span.end if diagnostic.span is not None else None,
        )
        for diagnostic in result.diagnostics
    ] == [("REF002", r"reference text: \eqref{missing}", target_start, target_start + 7)]

    graph = graph_documents((document,), config=Config())
    assert [(node.kind, node.label, node.source) for node in graph.nodes] == [
        ("reference", "missing", "latex_eqref")
    ]


@pytest.mark.public_regression
def test_public_check_hides_nested_legacy_block_but_keeps_outside_block() -> None:
    source = r"""\begin{equation}
$$
x =
$$
\eqref{raw-missing}
\end{equation}

$$
y =
$$
"""
    document = doc(source)

    result = check_documents((document,), config=Config())
    target_start = source.index("raw-missing")
    outside_start = source.index("y =")
    assert result.files_checked == 1
    assert result.math_blocks_checked == 1
    assert [
        (
            diagnostic.code,
            diagnostic.detail,
            diagnostic.span.start if diagnostic.span is not None else None,
            diagnostic.span.end if diagnostic.span is not None else None,
        )
        for diagnostic in result.diagnostics
    ] == [
        ("REF002", r"reference text: \eqref{raw-missing}", target_start, target_start + 11),
        ("PARSE020", None, outside_start, outside_start + 3),
    ]


@pytest.mark.public_regression
def test_public_unmatched_dollar_owns_later_raw_environment() -> None:
    source = (
        "\\begin{equation}\n"
        "x = 1 \\label{before} \\eqref{missing}\n"
        "\\end{equation}\n\n"
        "$$\n"
        "\\begin{equation}\n"
        "y = 2 \\label{leaked}\n"
        "\\end{equation}\n"
    )
    document = doc(source)

    result = check_documents((document,), config=Config())
    target_start = source.index("missing")
    dollar_start = source.index("$$")
    assert result.files_checked == 1
    assert result.math_blocks_checked == 0
    assert [
        (
            diagnostic.code,
            diagnostic.detail,
            diagnostic.span.start if diagnostic.span is not None else None,
            diagnostic.span.end if diagnostic.span is not None else None,
        )
        for diagnostic in result.diagnostics
    ] == [
        ("REF002", r"reference text: \eqref{missing}", target_start, target_start + 7),
        ("SCAN001", None, dollar_start, dollar_start + 2),
    ]

    graph = graph_documents((document,), config=Config())
    assert [(node.kind, node.label, node.source) for node in graph.nodes] == [
        ("equation", "before", "latex_label"),
        ("reference", "missing", "latex_eqref"),
    ]
    assert [(edge.target_label, edge.raw, edge.source_kind) for edge in graph.edges] == [
        ("missing", r"\eqref{missing}", "latex_eqref")
    ]


@pytest.mark.parametrize("role", ["ref", "eq", "numref"])
def test_myst_reference_role_owns_raw_latex_like_body(role: str) -> None:
    raw_body = r"\begin{equation}x = 1 \label{inside}\end{equation}"
    source = f"{{{role}}}`{raw_body}`"

    snapshot = lower(doc(source))

    assert snapshot.display_math == ()
    assert snapshot.equation_labels == ()
    if role == "ref":
        assert [(fact.role_kind, fact.target) for fact in snapshot.generic_refs] == [
            ("ref", raw_body)
        ]
        assert snapshot.equation_refs == ()
    else:
        assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
            (role, raw_body)
        ]
        assert snapshot.generic_refs == ()


def test_markdown_link_opener_keeps_ownership_before_raw_environment() -> None:
    source = r"""[inside \begin{equation}x = 1\end{equation}](#target)
"""

    snapshot = lower(doc(source))

    assert [(fact.role_kind, fact.target) for fact in snapshot.generic_refs] == [
        ("markdown-link", "target")
    ]
    assert snapshot.display_math == ()


@pytest.mark.parametrize(
    ("prefix", "expected_labels"),
    [
        pytest.param(
            "% ",
            ["live", "outer"],
            id="percent-content",
        ),
        pytest.param(
            "\\",
            ["live", "outer"],
            id="one-preceding-backslash",
        ),
        pytest.param(
            "\\\\",
            ["live", "outer"],
            id="two-preceding-backslashes",
        ),
    ],
)
def test_raw_verbatim_closer_is_exact_after_percent_or_backslashes(
    prefix: str,
    expected_labels: list[str],
) -> None:
    source = (
        "\\begin{equation}\n"
        "\\begin{verbatim}" + prefix + "\\end{verbatim} \\label{live}\n"
        "\\label{outer}\n"
        "\\end{equation}\n"
    )

    snapshot = lower(doc(source))

    assert [(fact.container, fact.complete) for fact in snapshot.display_math] == [("ams", True)]
    assert [fact.label for fact in snapshot.equation_labels] == expected_labels


def test_raw_verbatim_matching_star_and_mismatched_closer_keep_only_live_facts() -> None:
    source = r"""\begin{equation}
\begin{verbatim*}
\label{hidden}
\end{verbatim}
\label{still-hidden}
\end{verbatim*}
\label{live}
\end{equation}
"""

    snapshot = lower(doc(source))

    assert [(fact.container, fact.complete) for fact in snapshot.display_math] == [("ams", True)]
    assert [fact.label for fact in snapshot.equation_labels] == ["live"]


def test_unclosed_verbatim_in_dollar_display_hides_remaining_reference_facts() -> None:
    source = r"""$$
\label{visible}
\begin{verbatim}
\label{hidden}
\eqref{hidden}
$$
"""

    snapshot = lower(doc(source))

    assert [(fact.container, fact.complete) for fact in snapshot.display_math] == [
        ("dollar-dollar", True)
    ]
    assert [fact.label for fact in snapshot.equation_labels] == ["visible"]
    assert snapshot.equation_refs == ()


@pytest.mark.parametrize(
    ("source", "expected_display", "expected_generated"),
    [
        pytest.param(
            r"""\[
\begin{equation}
x = 1
\end{equation}
\]
""",
            (),
            (("bracketed-block", True),),
            id="bracket-first-complete",
        ),
        (
            r"""\begin{equation}
\[
x = 1
\]
\end{equation}
""",
            (("ams", "equation", True),),
            (),
        ),
        pytest.param(
            r"""\[
\begin{equation}
x = 1
""",
            (),
            (("bracketed-block", False),),
            id="bracket-first-incomplete",
        ),
        (
            r"""\begin{equation}
\[
x = 1
""",
            (("raw-latex", "equation", False),),
            (),
        ),
    ],
)
def test_bracketed_and_raw_math_use_the_earliest_opener_without_overlap(
    source: str,
    expected_display: tuple[tuple[str, str, bool], ...],
    expected_generated: tuple[tuple[str, bool], ...],
) -> None:
    snapshot = lower(doc(source))

    assert [
        (fact.container, fact.environment, fact.complete) for fact in snapshot.display_math
    ] == list(expected_display)
    assert [(fact.kind, fact.complete) for fact in snapshot.generated_formulas] == list(
        expected_generated
    )
    assert all(
        display.span is None
        or generated.span is None
        or display.span.end <= generated.span.start
        or generated.span.end <= display.span.start
        for display in snapshot.display_math
        for generated in snapshot.generated_formulas
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


@pytest.mark.parametrize("environment", ["flalign", "flalign*"])
def test_raw_flalign_environments_follow_supported_math_classification(
    environment: str,
) -> None:
    source = rf"""\begin{{{environment}}}
x &= y \label{{flalign-label}}
\eqref{{flalign-label}}
\end{{{environment}}}
"""

    snapshot = lower(doc(source))

    assert [(fact.container, fact.environment) for fact in snapshot.display_math] == [
        ("ams", environment)
    ]
    assert [fact.label for fact in snapshot.equation_labels] == ["flalign-label"]
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-eqref", "flalign-label")
    ]
    assert snapshot.unknown_math == ()


def test_starred_equation_environment_remains_supported_math() -> None:
    source = r"""\begin{equation*}
x = 1 \label{starred-equation}
\eqref{starred-equation}
\end{equation*}
"""

    snapshot = lower(doc(source))

    assert [(fact.container, fact.environment) for fact in snapshot.display_math] == [
        ("ams", "equation*")
    ]
    assert [fact.label for fact in snapshot.equation_labels] == ["starred-equation"]
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-eqref", "starred-equation")
    ]
    assert snapshot.unknown_math == ()


def test_escaped_raw_equation_markers_and_empty_targets_are_not_facts() -> None:
    source = r"""\begin{equation}
x = y \\label{escaped} \\ref{escaped} \ref{ }
\end{equation}
"""

    snapshot = lower(doc(source))

    assert snapshot.equation_labels == ()
    assert snapshot.equation_refs == ()
    assert snapshot.unknown_math == ()


def test_myst_and_raw_tex_labels_reject_blank_and_multiline_values() -> None:
    source = (
        "$$\n"
        "\\label{dollar-valid}\n"
        "\\label{ }\n"
        "\\label{dollar-bad\n"
        "line}\n"
        "\\ref{dollar-valid} \\ref{ } \\ref{dollar-bad\n"
        "line}\n"
        "$$\n"
        "\n"
        "```math\n"
        "\\label{fence-valid}\n"
        "\\label{ }\n"
        "\\label{fence-bad\n"
        "line}\n"
        "```\n"
        "\n"
        "```{math}\n"
        ":label:\n"
        ":label: directive-valid\n"
        "x = 1\n"
        "```\n"
        "\n"
        "\\begin{equation}\n"
        "\\label{raw-valid}\n"
        "\\label{ }\n"
        "\\label{raw-bad\n"
        "line}\n"
        "\\ref{raw-valid} \\ref{ } \\ref{raw-bad\n"
        "line}\n"
        "\\end{equation}\n"
    )

    snapshot = lower(doc(source))

    assert [label.label for label in snapshot.equation_labels] == [
        "fence-valid",
        "directive-valid",
        "dollar-valid",
        "raw-valid",
    ]
    assert [reference.target for reference in snapshot.equation_refs] == [
        "dollar-valid",
        "raw-valid",
    ]
    for label in snapshot.equation_labels:
        assert label.span is not None
        assert source[label.span.start : label.span.end] == label.label
    for reference in snapshot.equation_refs:
        assert reference.target_span is not None
        assert source[reference.target_span.start : reference.target_span.end] == reference.target


@pytest.mark.parametrize("environment", ["cases", "mystery"])
def test_unknown_raw_environment_preserves_parseable_equation_facts(
    environment: str,
) -> None:
    source = rf"""\begin{{{environment}}}
x & \text{{if }} y \label{{piecewise}}
\ref{{outside}}
\end{{{environment}}}
"""

    snapshot = lower(doc(source))

    assert len(snapshot.display_math) == 1
    assert snapshot.display_math[0].container == "raw-latex"
    assert [fact.label for fact in snapshot.equation_labels] == ["piecewise"]
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-ref", "outside")
    ]
    assert [
        (fact.source_math_fact_id, fact.reason, fact.excerpt) for fact in snapshot.unknown_math
    ] == [(snapshot.display_math[0].fact_id, "environment", environment)]


def test_math_host_classification_is_idempotent_for_unsupported_raw_environment() -> None:
    source = r"""\begin{mystery}
x = 1 \label{one} \ref{two}
\end{mystery}
"""

    first = lower(doc(source))
    second = MathHost().classify(first)

    assert second == first


@pytest.mark.parametrize(
    ("source", "expected_display", "expected_unknown", "expected_generated"),
    [
        pytest.param(
            "\\begin{cases}\nformula-not-decoded\n\\end{cases}\n",
            (("raw-latex", "cases", True),),
            (("environment", "cases"),),
            (),
            id="unsupported-complete",
        ),
        pytest.param(
            "\\begin{equation}\nformula-not-decoded\n",
            (("raw-latex", "equation", False),),
            (("parse_limit", "equation"),),
            (),
            id="recognized-incomplete",
        ),
        pytest.param(
            "\\begin{equation}\nformula-not-decoded\n\\end{equation}\n",
            (("ams", "equation", True),),
            (),
            (("placeholder", "formula-not-decoded"),),
            id="recognized-complete",
        ),
    ],
)
def test_raw_formula_markers_follow_classified_display_ownership(
    source: str,
    expected_display: tuple[tuple[str, str, bool], ...],
    expected_unknown: tuple[tuple[str, str], ...],
    expected_generated: tuple[tuple[str, str], ...],
) -> None:
    snapshot = lower(doc(source))

    assert [
        (fact.container, fact.environment, fact.complete) for fact in snapshot.display_math
    ] == list(expected_display)
    assert [(fact.reason, fact.excerpt) for fact in snapshot.unknown_math] == list(expected_unknown)
    assert [(fact.kind, fact.placeholder_kind) for fact in snapshot.generated_formulas] == list(
        expected_generated
    )


@pytest.mark.parametrize("environment", ["equation1", "my-env:foo"])
def test_custom_raw_environment_tokens_preserve_equation_facts(environment: str) -> None:
    source = rf"""\begin{{{environment}}}
x = 1 \label{{custom-label}}
\ref{{custom-label}}
\end{{{environment}}}
"""

    snapshot = lower(doc(source))

    assert [(fact.container, fact.environment) for fact in snapshot.display_math] == [
        ("raw-latex", environment)
    ]
    assert [fact.label for fact in snapshot.equation_labels] == ["custom-label"]
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-ref", "custom-label")
    ]
    assert [(fact.reason, fact.excerpt) for fact in snapshot.unknown_math] == [
        ("environment", environment)
    ]


@pytest.mark.parametrize("environment", ["equation1", "my-env:foo"])
def test_unclosed_custom_raw_environment_is_unknown_without_equation_facts(
    environment: str,
) -> None:
    source = rf"""\begin{{{environment}}}
x = 1 \label{{partial}}
\ref{{missing}}
"""

    snapshot = lower(doc(source))

    assert [(fact.environment, fact.complete) for fact in snapshot.display_math] == [
        (environment, False)
    ]
    assert snapshot.equation_labels == ()
    assert snapshot.equation_refs == ()
    assert [(fact.reason, fact.excerpt) for fact in snapshot.unknown_math] == [
        ("environment", environment)
    ]


@pytest.mark.parametrize(
    "environment",
    ["figure", "table", "itemize", "document", "verbatim", "verbatim*"],
)
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


def test_nonmath_raw_environment_owns_formula_placeholder_candidates() -> None:
    source = r"""\begin{figure}

formula-not-decoded

![formula placeholder](equation-placeholder.svg)

\end{figure}

formula-not-decoded

![formula placeholder](equation-placeholder-outside.svg)
"""

    snapshot = lower(doc(source))
    placeholders = tuple(
        fact for fact in snapshot.generated_formulas if fact.placeholder_kind is not None
    )

    assert [(fact.kind, fact.placeholder_kind, fact.text) for fact in placeholders] == [
        ("placeholder", "formula-not-decoded", "formula-not-decoded"),
        (
            "image-placeholder",
            "formula-image",
            "![formula placeholder](equation-placeholder-outside.svg)",
        ),
    ]


@pytest.mark.parametrize("environment", ["figure*", "table*"])
def test_starred_nonmath_raw_environments_are_opaque(environment: str) -> None:
    source = rf"""\begin{{{environment}}}
\A t t e n t {{x}}
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


def test_nested_verbatim_environment_does_not_leak_equation_facts() -> None:
    source = r"""\begin{equation}
\label{live}
\begin{verbatim}
\begin{align}
\label{hidden} \ref{hidden}
\end{verbatim}
\eqref{live}
\end{equation}
"""

    snapshot = lower(doc(source))

    assert [fact.label for fact in snapshot.equation_labels] == ["live"]
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-eqref", "live")
    ]


@pytest.mark.parametrize(
    "environment", ["document", "figure", "figure*", "itemize", "table", "table*"]
)
def test_nested_nonmath_raw_environments_do_not_leak_equation_facts(environment: str) -> None:
    source = rf"""\begin{{equation}}
\begin{{{environment}}}
\label{{hidden}} \ref{{hidden}}
\end{{{environment}}}
\label{{live}} \eqref{{live}}
\end{{equation}}
"""

    snapshot = lower(doc(source))

    assert [fact.label for fact in snapshot.equation_labels] == ["live"]
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-eqref", "live")
    ]


@pytest.mark.parametrize("environment", ["figure", "verbatim"])
def test_dollar_display_ignores_nested_nonmath_environment_facts(environment: str) -> None:
    source = rf"""$$
\begin{{{environment}}}
\label{{hidden}} \eqref{{hidden}}
\end{{{environment}}}
\label{{live}} \eqref{{live}}
$$
"""

    snapshot = lower(doc(source))

    assert [(fact.container, fact.environment) for fact in snapshot.display_math] == [
        ("dollar-dollar", None)
    ]
    assert [fact.label for fact in snapshot.equation_labels] == ["live"]
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-eqref", "live")
    ]


@pytest.mark.parametrize("environment", ["figure", "verbatim"])
def test_dollar_display_valid_outer_align_ignores_nested_nonmath_environment(
    environment: str,
) -> None:
    source = rf"""$$
\begin{{align}}
a &= b
\begin{{{environment}}}
\label{{hidden}} \eqref{{hidden}}
\end{{{environment}}}
c &= d \label{{live}} \eqref{{live}}
\end{{align}}
$$
"""

    snapshot = lower(doc(source))

    assert [(fact.container, fact.environment) for fact in snapshot.display_math] == [
        ("ams", "align")
    ]
    assert [fact.label for fact in snapshot.equation_labels] == ["live"]
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-eqref", "live")
    ]


def test_dollar_display_valid_outer_align_keeps_equation_facts_without_opaque_environment() -> None:
    source = r"""$$
\begin{align}
a &= b \label{live} \eqref{live}
\end{align}
$$
"""

    snapshot = lower(doc(source))

    assert [(fact.container, fact.environment) for fact in snapshot.display_math] == [
        ("ams", "align")
    ]
    assert [fact.label for fact in snapshot.equation_labels] == ["live"]
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-eqref", "live")
    ]


def test_mismatched_nested_raw_environment_stays_partial_without_equation_facts() -> None:
    source = r"""\begin{equation}
\begin{aligned}
\end{gather}
\end{aligned}
\label{partial}
\end{equation}
"""

    snapshot = lower(doc(source))

    assert [(fact.environment, fact.complete) for fact in snapshot.display_math] == [
        ("equation", False)
    ]
    assert snapshot.equation_labels == ()
    assert snapshot.equation_refs == ()
    assert [(fact.reason, fact.excerpt) for fact in snapshot.unknown_math] == [
        ("parse_limit", "equation")
    ]


@pytest.mark.parametrize(
    "source",
    [
        r"Text $\begin{equation}x = 1\end{equation}$.",
        r"Text {math}`\begin{equation}x = 1\end{equation}`.",
        r"Text \(\begin{equation}x = 1\end{equation}\).",
    ],
    ids=("dollar", "myst-role", "latex-paren"),
)
def test_inline_opener_before_raw_environment_owns_the_candidate(source: str) -> None:
    snapshot = lower(doc(source))

    assert len(snapshot.inline_math) == 1
    assert snapshot.inline_math[0].delimiter_kind in {"dollar", "myst-role", "latex-paren"}
    assert snapshot.display_math == ()
    assert len(snapshot.unknown_math) == 1
    assert snapshot.unknown_math[0].reason == "environment"


@pytest.mark.parametrize(
    "source",
    [
        r"\begin{equation}$x = 1$\end{equation}",
        r"\begin{equation}{math}`x = 1`\end{equation}",
        r"\begin{equation}\(x = 1\)\end{equation}",
    ],
    ids=("dollar", "myst-role", "latex-paren"),
)
def test_raw_opener_before_inline_math_owns_the_candidate(source: str) -> None:
    snapshot = lower(doc(source))

    assert [(fact.container, fact.environment) for fact in snapshot.display_math] == [
        ("ams", "equation")
    ]
    assert snapshot.inline_math == ()


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


def test_raw_environment_inside_markdown_link_label_is_opaque() -> None:
    source = (
        "[\\begin{equation}\n"
        "x = 1 \\label{hidden}\n"
        "formula-not-decoded\n"
        "\\end{equation}](#target)\n\n"
        "\\begin{equation}\n"
        "x = 1 \\label{live}\n"
        "\\end{equation}\n"
    )

    snapshot = lower(doc(source))

    assert [label.label for label in snapshot.equation_labels] == ["live"]
    assert [fact.container for fact in snapshot.display_math] == ["ams"]
    assert snapshot.generated_formulas == ()


@pytest.mark.parametrize(
    ("source", "expected_containers"),
    [
        (
            "\\begin{figure}\n$$\nx = 1\n$$\n\\end{figure}\n",
            (),
        ),
        (
            "$$\n\\begin{figure}\nx = 1\n\\end{figure}\n$$\n",
            ("dollar-dollar",),
        ),
    ],
    ids=("raw-opens-first", "math-opens-first"),
)
def test_raw_and_dollar_math_have_source_ordered_ownership(
    source: str,
    expected_containers: tuple[str, ...],
) -> None:
    snapshot = lower(doc(source))

    assert tuple(fact.container for fact in snapshot.display_math) == expected_containers
    assert snapshot.equation_labels == ()
    assert snapshot.equation_refs == ()
    assert snapshot.generated_formulas == ()
    if expected_containers:
        [display] = snapshot.display_math
        assert display.span is not None
        assert source[display.span.start : display.span.end] == source[3:-3].rstrip("\n")


@pytest.mark.parametrize(
    ("source", "expected_containers"),
    [
        (
            "\\begin{equation}\n```math\nx = 1\n```\n\\end{equation}\n",
            ("ams",),
        ),
        (
            "```math\n\\begin{equation}\nx = 1\n\\end{equation}\n```\n",
            ("fenced-math",),
        ),
    ],
    ids=("raw-opens-first", "fence-opens-first"),
)
def test_raw_and_fenced_math_have_source_ordered_ownership(
    source: str,
    expected_containers: tuple[str, ...],
) -> None:
    snapshot = lower(doc(source))

    assert tuple(fact.container for fact in snapshot.display_math) == expected_containers
    assert snapshot.equation_labels == ()
    assert snapshot.equation_refs == ()


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
    assert snapshot.equation_labels == ()
    assert snapshot.equation_refs == ()
    assert [(fact.reason, fact.excerpt) for fact in snapshot.unknown_math] == [
        ("parse_limit", "equation")
    ]


def test_mismatched_raw_environment_is_partial_unknown_without_equation_facts() -> None:
    source = r"""\begin{mystery}
x = y \label{partial-unknown}
\end{equation}
"""

    snapshot = lower(doc(source))

    assert len(snapshot.display_math) == 1
    assert snapshot.display_math[0].container == "raw-latex"
    assert snapshot.display_math[0].complete is False
    assert snapshot.equation_labels == ()
    assert snapshot.equation_refs == ()
    assert [(fact.reason, fact.excerpt) for fact in snapshot.unknown_math] == [
        ("environment", "mystery")
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


def test_raw_math_ignores_active_tex_comments_for_environment_labels_and_refs() -> None:
    source = r"""\begin{equation}
% \begin{align}
x = y % \label{commented} \eqref{commented}
\label{real}
\eqref{missing}
% \end{align}
\end{equation}
"""

    snapshot = lower(doc(source))

    assert [(fact.container, fact.complete) for fact in snapshot.display_math] == [("ams", True)]
    assert [fact.label for fact in snapshot.equation_labels] == ["real"]
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("tex-eqref", "missing")
    ]


def test_raw_equation_facts_are_deterministic_after_newline_normalization() -> None:
    lf = lower(doc("\\begin{equation}\nx=1\\label{x}\n\\end{equation}\n"))
    crlf = lower(doc("\\begin{equation}\r\nx=1\\label{x}\r\n\\end{equation}\r\n"))

    assert lf.display_math == crlf.display_math
    assert lf.equation_labels == crlf.equation_labels
    assert lf.equation_refs == crlf.equation_refs
    assert lf.unknown_math == crlf.unknown_math
