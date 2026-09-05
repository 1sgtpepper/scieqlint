from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import SupportsIndex, overload

import pytest

from scieqlint.api import check_documents
from scieqlint.config.model import Config, ScannerConfig
from scieqlint.facts.math import InlineMathFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath("generated.md"), text, DocumentKind.MARKDOWN)


def _classify(snapshot: FactSnapshot) -> FactSnapshot:
    from scieqlint.parse.math import MathHost

    return MathHost().classify(snapshot)


def test_inline_math_facts_preserve_delimiters_roles_status_and_exact_spans() -> None:
    source = (Path(__file__).parent / "fixtures" / "generated" / "inline_math_facts.md").read_text(
        encoding="utf-8"
    )

    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    assert [fact.delimiter_kind for fact in snapshot.inline_math] == [
        "dollar",
        "myst-role",
        "latex-paren",
        "plain-text",
        "dollar",
    ]
    assert [fact.body for fact in snapshot.inline_math] == [
        "E = mc^2",
        "x_i + y_i",
        "z = 3",
        "a = b+c",
        r"\begin{aligned}x&=1\end{aligned}",
    ]
    assert [fact.surrounding_text_role for fact in snapshot.inline_math] == [
        "heading",
        "paragraph",
        "paragraph",
        "list-item",
        "blockquote",
    ]
    assert [fact.parse_status for fact in snapshot.inline_math] == [
        "preserved",
        "preserved",
        "preserved",
        "text-leak",
        "unsupported",
    ]
    assert all(fact.span is not None for fact in snapshot.inline_math)
    assert [
        source[fact.span.start : fact.span.end] for fact in snapshot.inline_math if fact.span
    ] == [
        "E = mc^2",
        "x_i + y_i",
        "z = 3",
        "a = b+c",
        r"\begin{aligned}x&=1\end{aligned}",
    ]


def test_inline_math_role_respects_ordered_list_marker_width() -> None:
    snapshot = _classify(MySTFrontend().lower((doc("123456789. a = b\n\n1234567890. c = d\n"),)))

    assert [fact.surrounding_text_role for fact in snapshot.inline_math] == [
        "list-item",
        "paragraph",
    ]


def test_plain_text_math_in_setext_heading_keeps_heading_role() -> None:
    snapshot = _classify(MySTFrontend().lower((doc("a = b\n---\n"),)))

    assert [fact.surrounding_text_role for fact in snapshot.inline_math] == ["heading"]


def test_math_host_classifies_malformed_and_unsupported_inline_math() -> None:
    snapshot = _classify(
        MySTFrontend().lower(
            (
                doc(
                    r"Bad $\frac{1}{$ and trailing $x +$ and unsupported "
                    r"$\begin{aligned}x&=1\end{aligned}$.",
                ),
            )
        )
    )

    assert [fact.parse_status for fact in snapshot.inline_math] == [
        "unsupported",
        "unsupported",
        "unsupported",
    ]
    assert [(fact.reason, fact.excerpt) for fact in snapshot.unknown_math] == [
        ("unsupported_syntax", r"\frac{1}{"),
        ("unsupported_syntax", "x +"),
        ("environment", "aligned"),
    ]


def test_math_host_keeps_ordinary_prose_out_of_plain_text_math() -> None:
    snapshot = _classify(
        MySTFrontend().lower((doc("Version 1 < 2; Status = complete; A>=B; a = b+c."),))
    )

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        ("1 < 2", "not-math"),
        ("Status = complete", "not-math"),
        ("A>=B", "text-leak"),
        ("a = b+c", "text-leak"),
    ]
    assert [fact.body for fact in QueryHost(snapshot).math.inline_math()] == [
        "A>=B",
        "a = b+c",
    ]


def test_portability_query_excludes_inferred_plain_text_math() -> None:
    snapshot = _classify(MySTFrontend().lower((doc("Status = complete; a = b+c; $x$"),)))

    assert [
        (fact.delimiter_kind, fact.body, fact.parse_status) for fact in snapshot.inline_math
    ] == [
        ("plain-text", "Status = complete", "not-math"),
        ("plain-text", "a = b+c", "text-leak"),
        ("dollar", "x", "preserved"),
    ]
    assert [fact.body for fact in QueryHost(snapshot).portability.inline_math_missing_alt()] == [
        "x"
    ]


def test_plain_text_math_preserves_decimal_atoms_and_exact_spans() -> None:
    source = "x = 3.14\n3.14 = x\nE = 0.5*m*v^2\n.50 = x\n"

    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        ("x = 3.14", "text-leak"),
        ("3.14 = x", "text-leak"),
        ("E = 0.5*m*v^2", "text-leak"),
        (".50 = x", "text-leak"),
    ]
    assert all(fact.span is not None for fact in snapshot.inline_math)
    assert [
        source[fact.span.start : fact.span.end] for fact in snapshot.inline_math if fact.span
    ] == ["x = 3.14", "3.14 = x", "E = 0.5*m*v^2", ".50 = x"]


def test_decimal_prose_candidates_remain_excluded_from_math_queries() -> None:
    snapshot = _classify(
        MySTFrontend().lower((doc("Version 2.0 = complete; threshold 1.5 < 2.0."),))
    )

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        ("2.0 = complete", "not-math"),
        ("1.5 < 2.0", "not-math"),
    ]
    assert QueryHost(snapshot).math.inline_math() == ()


@pytest.mark.parametrize(
    ("source", "forbidden_prefix"),
    [
        ("x = f(y)", "x = f"),
        (r"x = \frac{1}{2}", r"x = \frac"),
        ("x = f[y]", "x = f"),
    ],
)
def test_plain_text_math_never_emits_truncated_operand_prefix(
    source: str,
    forbidden_prefix: str,
) -> None:
    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    for facts in (snapshot.inline_math, QueryHost(snapshot).math.inline_math()):
        assert forbidden_prefix not in {fact.body for fact in facts}
        assert all(fact.body == source for fact in facts)


def test_plain_text_arithmetic_signal_is_symmetric_across_the_relation() -> None:
    snapshot = _classify(MySTFrontend().lower((doc("1+1=2\n2=1+1\n12/3=4\n4=12/3\n1 < 2\n"),)))

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        ("1+1=2", "text-leak"),
        ("2=1+1", "text-leak"),
        ("12/3=4", "text-leak"),
        ("4=12/3", "text-leak"),
        ("1 < 2", "not-math"),
    ]
    assert [fact.body for fact in QueryHost(snapshot).math.inline_math()] == [
        "1+1=2",
        "2=1+1",
        "12/3=4",
        "4=12/3",
    ]


def test_plain_text_math_preserves_attached_unary_signs_and_exact_spans() -> None:
    source = "-1 = x\nx = -1\n-x = y\nT = -273.15\nStatus = -complete\n"

    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        ("-1 = x", "text-leak"),
        ("x = -1", "text-leak"),
        ("-x = y", "text-leak"),
        ("T = -273.15", "text-leak"),
        ("Status = -complete", "not-math"),
    ]
    assert all(fact.span is not None for fact in snapshot.inline_math)
    assert [
        source[fact.span.start : fact.span.end]
        for fact in snapshot.inline_math
        if fact.span is not None
    ] == [fact.body for fact in snapshot.inline_math]
    assert [fact.body for fact in QueryHost(snapshot).math.inline_math()] == [
        "-1 = x",
        "x = -1",
        "-x = y",
        "T = -273.15",
    ]


@pytest.mark.parametrize(
    ("source", "expected_role"),
    [
        ("- explanatory\n  continued with a = b+c\n", "list-item"),
        ("- explanatory\ncontinued with a = b+c\n", "list-item"),
        ("> explanatory\ncontinued with a = b+c\n", "blockquote"),
        ("> - explanatory\n>   continued with a = b+c\n", "blockquote"),
    ],
)
def test_inline_math_inherits_shared_markdown_container_role(
    source: str,
    expected_role: str,
) -> None:
    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        ("a = b+c", "text-leak")
    ]
    fact = snapshot.inline_math[0]
    assert fact.surrounding_text_role == expected_role
    assert fact.span is not None
    assert source[fact.span.start : fact.span.end] == "a = b+c"


def test_math_host_requires_structural_signal_around_plain_text_operators() -> None:
    snapshot = _classify(
        MySTFrontend().lower(
            (
                doc(
                    "input/output = enabled; Status/Result = complete; yes/no = maybe; "
                    "x/y = z; p*q = r; a = b+c; x_i = velocity; "
                    "velocity = distance / time."
                ),
            )
        )
    )

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        ("input/output = enabled", "not-math"),
        ("Status/Result = complete", "not-math"),
        ("yes/no = maybe", "not-math"),
        ("x/y = z", "text-leak"),
        ("p*q = r", "text-leak"),
        ("a = b+c", "text-leak"),
        ("x_i = velocity", "text-leak"),
        ("velocity = distance / time", "text-leak"),
    ]
    assert [fact.body for fact in QueryHost(snapshot).math.inline_math()] == [
        "x/y = z",
        "p*q = r",
        "a = b+c",
        "x_i = velocity",
        "velocity = distance / time",
    ]


def test_math_host_owns_plain_text_candidate_classification() -> None:
    lowered = MySTFrontend().lower((doc("compact a = b+c."),))

    assert [(fact.body, fact.parse_status) for fact in lowered.inline_math] == [
        ("a = b+c", "candidate"),
    ]
    classified = _classify(lowered)
    assert [(fact.body, fact.parse_status) for fact in classified.inline_math] == [
        ("a = b+c", "text-leak"),
    ]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a = b = c", (("a = b = c", "text-leak"),)),
        ("a = b +", ()),
        ("a = b /", ()),
        ("a = b c", ()),
        (r"x = \frac y", ()),
        (r"x = \sqrt x", ()),
        (r"\frac x y = z", ()),
        ("x = f y", ()),
        ("x = a)", ()),
        ("a = b + c prose", ()),
        ("a = b + c d", ()),
        ("a = b + c d = e", ()),
        ("a = - b + c = d; e = f", (("e = f", "text-leak"),)),
        ("a = b (c); d = e", (("d = e", "text-leak"),)),
        (
            "a = b, c = d",
            (("a = b", "text-leak"), ("c = d", "text-leak")),
        ),
        (
            "a = b + c; d = e",
            (("a = b + c", "text-leak"), ("d = e", "text-leak")),
        ),
        ("a = b + c", (("a = b + c", "text-leak"),)),
    ],
)
def test_plain_text_candidates_do_not_publish_truncated_prefixes(
    source: str,
    expected: tuple[tuple[str, str], ...],
) -> None:
    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == list(expected)


def test_check_documents_preserves_display_math_when_inline_math_is_disabled(monkeypatch) -> None:
    from scieqlint.parse.math import MathHost

    source = "$$\n\\sin(x) = x\n$$\n$x$\n"
    observed = []
    original_classify = MathHost.classify

    def capture_classification(self, snapshot):
        classified = original_classify(self, snapshot)
        observed.append(classified)
        return classified

    monkeypatch.setattr(MathHost, "classify", capture_classification)

    disabled = check_documents((doc(source),), config=Config())
    assert disabled.math_blocks_checked == 1
    assert [(diagnostic.code, diagnostic.equation) for diagnostic in disabled.diagnostics] == [
        ("PARSE021", r"\sin(x) = x")
    ]
    assert len(observed) == 1
    assert [fact.body for fact in observed[0].display_math] == [r"\sin(x) = x"]
    assert observed[0].inline_math == ()

    enabled = check_documents(
        (doc(source),),
        config=Config(scanner=ScannerConfig(inline_math=True)),
    )
    assert enabled.math_blocks_checked == 2
    assert len(observed) == 2
    assert [(fact.body, fact.parse_status) for fact in observed[1].inline_math] == [
        ("x", "preserved")
    ]
    assert [fact.body for fact in observed[1].display_math] == [r"\sin(x) = x"]


def test_latex_paren_math_survives_percent_in_prose() -> None:
    snapshot = _classify(MySTFrontend().lower((doc(r"100% complete \(x\)"),)))

    assert [
        (fact.delimiter_kind, fact.body, fact.parse_status) for fact in snapshot.inline_math
    ] == [("latex-paren", "x", "preserved")]


def test_math_host_rejects_plain_prose_and_mismatched_delimiters() -> None:
    prose = InlineMathFact(
        fact_id="prose",
        document_id="generated.md",
        span=None,
        raw="ordinary prose",
        body="ordinary prose",
        delimiter_kind="plain-text",
    )
    mismatched = InlineMathFact(
        fact_id="mismatched",
        document_id="generated.md",
        span=None,
        raw="(x]",
        body="(x]",
        delimiter_kind="dollar",
    )

    snapshot = _classify(FactSnapshot(inline_math=(prose, mismatched)))

    assert [fact.parse_status for fact in snapshot.inline_math] == [
        "not-math",
        "unsupported",
    ]
    assert [(fact.reason, fact.excerpt) for fact in snapshot.unknown_math] == [
        ("unsupported_syntax", "(x]"),
    ]


def test_inline_math_fact_scanning_ignores_code_fences_inline_code_and_ordinary_prose() -> None:
    source = "\n".join(
        (
            "Ordinary prose has words and punctuation but no equation candidate.",
            "",
            "<!-- hidden x = y -->",
            "",
            "[linked x = y](#target)",
            "",
            "`literal x = y`",
            "",
            "```text",
            "$inside = code$",
            "{math}`also = code`",
            "```",
        )
    )

    snapshot = MySTFrontend().lower((doc(source),))

    assert snapshot.inline_math == ()


@pytest.mark.parametrize(
    "source",
    [
        "x <em>y</em>",
        "a = {eq}`target`",
    ],
)
def test_plain_text_math_candidate_cannot_cross_owned_markdown_syntax(source: str) -> None:
    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    assert QueryHost(snapshot).math.inline_math() == ()


def test_inline_math_uses_link_aware_lexical_ownership_without_rescanning() -> None:
    source = "[link x = y](dest`meta) a = b+c; `literal p = q`"

    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    assert [fact.body for fact in QueryHost(snapshot).math.inline_math()] == ["a = b+c"]


@pytest.mark.parametrize(
    ("source", "delimiter_kind"),
    [
        ("[dollar $x$](target)", "dollar"),
        (r"[paren \(x\)](target)", "latex-paren"),
        ("[role {math}`x`](target)", "myst-role"),
    ],
    ids=["dollar", "latex-paren", "myst-role"],
)
def test_explicit_inline_math_in_link_labels_is_delimiter_independent(
    source: str,
    delimiter_kind: str,
) -> None:
    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    assert [
        (fact.delimiter_kind, fact.body, fact.parse_status) for fact in snapshot.inline_math
    ] == [(delimiter_kind, "x", "preserved")]
    fact = snapshot.inline_math[0]
    assert fact.span is not None
    assert source[fact.span.start : fact.span.end] == "x"
    assert QueryHost(snapshot).math.inline_math() == snapshot.inline_math


@pytest.mark.parametrize(
    "source",
    [
        '[label](target "$x$")',
        r'[label](target "\(x\)")',
        '[label](target "{math}`x`")',
        "[plain x = y](target)",
    ],
    ids=["dollar-title", "latex-paren-title", "myst-role-title", "inferred-label"],
)
def test_link_metadata_and_inferred_link_label_math_remain_opaque(source: str) -> None:
    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    assert snapshot.inline_math == ()
    assert QueryHost(snapshot).math.inline_math() == ()


def test_inline_math_facts_are_deterministic_across_newline_normalization() -> None:
    lf = MySTFrontend().lower((doc("Text $x = 1$.\n"),))
    crlf = MySTFrontend().lower((doc("Text $x = 1$.\r\n"),))

    assert lf.inline_math == crlf.inline_math


def test_empty_delimited_math_is_ignored_but_nonempty_math_is_preserved() -> None:
    snapshot = MySTFrontend().lower((doc(r"Empty \(\) and \(x = 1\)."),))

    assert [(fact.delimiter_kind, fact.body) for fact in snapshot.inline_math] == [
        ("latex-paren", "x = 1"),
    ]


def test_empty_myst_math_role_is_ignored_but_nonempty_role_is_preserved() -> None:
    snapshot = MySTFrontend().lower((doc(r"Empty {math}`   ` and {math}`x = 1`."),))

    assert [(fact.delimiter_kind, fact.body) for fact in snapshot.inline_math] == [
        ("myst-role", "x = 1"),
    ]


def test_mixed_inline_delimiters_have_one_owner() -> None:
    cases = (
        (r"\(a $b$ c\)", ("dollar", "b")),
        (r"$a \(b\) c$", ("dollar", r"a \(b\) c")),
    )

    for source, expected in cases:
        snapshot = _classify(MySTFrontend().lower((doc(source),)))

        assert [(fact.delimiter_kind, fact.body) for fact in snapshot.inline_math] == [expected]
        assert [fact.body for fact in QueryHost(snapshot).math.inline_math()] == [expected[1]], (
            source
        )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (r"{math}`\(\alpha\)`", (("myst-role", r"\(\alpha\)", r"{math}`\(\alpha\)`"),)),
        (r"\(a {math}`b` c\)", (("myst-role", "b", r"{math}`b`"),)),
        (
            r"{math}`x` and \(y\)",
            (("myst-role", "x", r"{math}`x`"), ("latex-paren", "y", r"\(y\)")),
        ),
    ],
)
def test_myst_roles_own_overlapping_latex_parens_without_hiding_adjacent_math(
    source: str,
    expected: tuple[tuple[str, str, str], ...],
) -> None:
    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    assert [(fact.delimiter_kind, fact.body, fact.raw) for fact in snapshot.inline_math] == list(
        expected
    )
    for fact in snapshot.inline_math:
        assert fact.span is not None
        assert source[fact.span.start : fact.span.end] == fact.body
    assert QueryHost(snapshot).math.inline_math() == snapshot.inline_math


@pytest.mark.parametrize(
    "source",
    [
        r"\( broken `code` then \(x = 1\)",
        r"\( broken <span>opaque</span> then \(x = 1\)",
        r"\( broken {role}`opaque` then \(x = 1\)",
        r"\( broken `100%` then \(x = 1\)",
        r"\( broken <span>100%</span> then \(x = 1\)",
        r"\( broken {role}`100%` then \(x = 1\)",
        r"\( broken `code` % then \(x = 1\)",
        r"\( broken <span>opaque</span> % then \(x = 1\)",
        r"\( broken {role}`opaque` % then \(x = 1\)",
    ],
)
def test_opaque_ranges_reset_unclosed_latex_parens_without_hiding_later_math(
    source: str,
) -> None:
    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    assert [(fact.delimiter_kind, fact.body) for fact in snapshot.inline_math] == [
        ("latex-paren", "x = 1")
    ]
    fact = snapshot.inline_math[0]
    assert fact.span is not None
    assert source[fact.span.start : fact.span.end] == "x = 1"
    assert fact.raw == r"\(x = 1\)"
    assert fact.fact_id == f"generated.md::inline-math::{source.index(fact.raw)}"


@pytest.mark.parametrize(
    "source",
    [
        "$$ unclosed {math}`x`",
        r"$$ unclosed \(x\)",
        r"$$ unclosed a = b",
    ],
    ids=["myst-role", "latex-paren", "plain-text"],
)
def test_unclosed_display_math_owns_remaining_inline_syntax(source: str) -> None:
    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    assert snapshot.display_math == ()
    assert snapshot.inline_math == ()
    assert snapshot.unknown_math == ()


def test_closed_display_math_releases_following_inline_syntax() -> None:
    snapshot = _classify(MySTFrontend().lower((doc("$$\nx = y\n$$\n{math}`z`"),)))

    assert [fact.body for fact in snapshot.display_math] == ["x = y"]
    assert [
        (fact.delimiter_kind, fact.body, fact.parse_status) for fact in snapshot.inline_math
    ] == [("myst-role", "z", "preserved")]


def test_latex_paren_does_not_pair_across_lines() -> None:
    snapshot = MySTFrontend().lower((doc("\\(orphan\n\nordinary prose\\)"),))

    assert snapshot.inline_math == ()


def test_unclosed_latex_paren_does_not_consume_next_line_pair() -> None:
    source = "\\(orphan\n\\(x\\)"

    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    assert [(fact.delimiter_kind, fact.body) for fact in snapshot.inline_math] == [
        ("latex-paren", "x")
    ]
    fact = snapshot.inline_math[0]
    assert fact.span is not None
    assert source[fact.span.start : fact.span.end] == "x"


def test_latex_paren_line_boundary_is_identical_for_lf_and_crlf() -> None:
    lf = MySTFrontend().lower((doc("\\(orphan\n\\(x\\)"),))
    crlf = MySTFrontend().lower((doc("\\(orphan\r\n\\(x\\)"),))

    assert lf.inline_math == crlf.inline_math
    assert [(fact.delimiter_kind, fact.body) for fact in lf.inline_math] == [("latex-paren", "x")]


def test_latex_paren_does_not_close_inside_tex_comment() -> None:
    snapshot = _classify(MySTFrontend().lower((doc(r"\(x % \)"),)))

    assert snapshot.inline_math == ()
    assert QueryHost(snapshot).math.inline_math() == ()


def test_latex_paren_percent_after_closed_candidate_keeps_following_math_active() -> None:
    snapshot = _classify(MySTFrontend().lower((doc(r"\(x\) % \(y\)"),)))

    assert [
        (fact.delimiter_kind, fact.body, fact.parse_status) for fact in snapshot.inline_math
    ] == [("latex-paren", "x", "preserved"), ("latex-paren", "y", "preserved")]


def test_latex_paren_allows_escaped_percent_before_closer() -> None:
    source = r"\(x \% \)"

    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        (r"x \%", "preserved")
    ]
    fact = snapshot.inline_math[0]
    assert fact.span is not None
    assert source[fact.span.start : fact.span.end] == fact.body


@pytest.mark.parametrize(
    ("complete", "incomplete"),
    [
        ("x ≤ y", "x ≤"),
        ("x ≥ y", "x ≥"),
        ("x → y", "x →"),
        (r"x \leq y", r"x \leq"),
        (r"x \geq y", r"x \geq"),
    ],
)
def test_math_host_rejects_only_incomplete_relation_tails(
    complete: str,
    incomplete: str,
) -> None:
    snapshot = _classify(MySTFrontend().lower((doc(f"${complete}$ and ${incomplete}$"),)))

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        (complete, "preserved"),
        (incomplete, "unsupported"),
    ]
    assert [(fact.reason, fact.excerpt) for fact in snapshot.unknown_math] == [
        ("unsupported_syntax", incomplete)
    ]
    assert QueryHost(snapshot).math.inline_math() == snapshot.inline_math


def test_math_host_keeps_underscore_version_prose_quiet() -> None:
    snapshot = _classify(MySTFrontend().lower((doc("Version_2 = complete"),)))

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        ("Version_2 = complete", "not-math"),
    ]
    assert QueryHost(snapshot).math.inline_math() == ()


@pytest.mark.parametrize("environment", ["foo-bar", "array2", "foo_bar"])
def test_math_host_classifies_unsupported_environment_name_variants(environment: str) -> None:
    body = rf"\begin{{{environment}}}x\end{{{environment}}}"
    snapshot = _classify(MySTFrontend().lower((doc(f"${body}$"),)))

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        (body, "unsupported")
    ]
    assert [(unknown.reason, unknown.excerpt) for unknown in snapshot.unknown_math] == [
        ("environment", environment)
    ]


def test_tex_delimiters_and_environments_use_full_escape_parity() -> None:
    even = "\\" * 2
    odd = "\\" * 3
    source = "\n".join(
        (
            "Escaped " + even + "(x+y" + even + ")",
            "Active " + odd + "(x+y" + odd + ")",
            "Escaped environment $" + even + "begin{aligned}x=y" + even + "end{aligned}$",
            "Active environment $" + odd + "begin{aligned}x=y" + odd + "end{aligned}$",
        )
    )

    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    assert [
        (fact.delimiter_kind, fact.body, fact.parse_status) for fact in snapshot.inline_math
    ] == [
        ("latex-paren", "x+y" + even, "preserved"),
        ("dollar", even + "begin{aligned}x=y" + even + "end{aligned}", "preserved"),
        ("dollar", odd + "begin{aligned}x=y" + odd + "end{aligned}", "unsupported"),
    ]
    assert [(fact.reason, fact.excerpt) for fact in snapshot.unknown_math] == [
        ("environment", "aligned")
    ]
    assert [
        source[fact.span.start : fact.span.end]
        for fact in snapshot.inline_math
        if fact.span is not None
    ] == [fact.body for fact in snapshot.inline_math]


def test_nested_latex_paren_delimiters_are_ambiguous_after_bounded_sweep() -> None:
    source = r"\(" + r"\(" * 32 + "x" + r"\)"

    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    [fact] = snapshot.inline_math
    assert fact.delimiter_kind == "latex-paren"
    assert fact.parse_status == "unsupported"
    assert fact.span is not None
    assert source[fact.span.start : fact.span.end] == r"\(" * 32 + "x"
    assert [(unknown.reason, unknown.excerpt) for unknown in snapshot.unknown_math] == [
        ("ambiguous_delimiter", r"\("),
    ]
    query = QueryHost(snapshot).math
    assert query.inline_math() == (fact,)
    assert query.unknown_math() == snapshot.unknown_math


def test_latex_paren_delimiter_ambiguity_respects_escape_parity() -> None:
    escaped_inner = "\\" * 2 + "(x)"
    source = r"\(x\)" + "\n" + r"\(" + escaped_inner + r"\)"

    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        ("x", "preserved"),
        (escaped_inner, "preserved"),
    ]
    assert snapshot.unknown_math == ()


def test_unmatched_latex_closer_does_not_hide_a_later_math_pair() -> None:
    snapshot = MySTFrontend().lower((doc(r"\) prose \(x = 1\)"),))

    assert [(fact.delimiter_kind, fact.body) for fact in snapshot.inline_math] == [
        ("latex-paren", "x = 1"),
    ]


def test_inline_dollar_environment_sweep_rejects_malformed_math_and_needs_closer() -> None:
    body = r"\begin{align} " * 32 + r"x + y \end{align}"
    source = "$" + body + "$"
    malformed = _classify(MySTFrontend().lower((doc(source),)))
    unclosed = _classify(MySTFrontend().lower((doc("$" + body),)))

    assert [(fact.body, fact.parse_status) for fact in malformed.inline_math] == [
        (body, "unsupported")
    ]
    assert [(fact.reason, fact.excerpt) for fact in malformed.unknown_math] == [
        ("environment", "align")
    ]
    span = malformed.inline_math[0].span
    assert span is not None
    assert source[span.start : span.end] == body
    assert unclosed.inline_math == ()


def test_inline_math_range_merge_discards_empty_ranges_and_merges_overlaps() -> None:
    from scieqlint.frontend.myst_math import _merge_occupied

    assert _merge_occupied(((4, 4), (8, 10), (9, 12), (20, 19))) == ((8, 12),)


class _IndexOnlyRanges(Sequence[tuple[int, int]]):
    def __init__(self, ranges: tuple[tuple[int, int], ...]) -> None:
        self._ranges = ranges
        self.accesses = 0

    def __getitem__(self, index: int) -> tuple[int, int]:
        if not isinstance(index, int):
            raise AssertionError("overlap lookup must not slice the occupied ranges")
        self.accesses += 1
        return self._ranges[index]

    def __len__(self) -> int:
        return len(self._ranges)

    def __iter__(self):
        raise AssertionError("overlap lookup must not rescan all occupied ranges")


def test_inline_overlap_lookup_has_bounded_index_work_per_candidate() -> None:
    from scieqlint.frontend.myst_math import _overlaps_occupied

    occupied = _IndexOnlyRanges(tuple((index * 4, index * 4 + 2) for index in range(128)))
    queries = tuple((index * 4 + 1, index * 4 + 3) for index in range(128))

    assert all(_overlaps_occupied(start, end, occupied) for start, end in queries)
    assert occupied.accesses <= len(queries) * (len(occupied).bit_length() + 1)


def test_math_host_respects_tex_comment_and_argument_token_boundaries() -> None:
    source = "\n".join(
        (
            r"$\frac{1}{2}% \frac$",
            r"$\frac{1}% the second argument is absent$",
            r"$\frac{1}{2}\% \frac$",
            r"$\frac\alpha$",
            r"$\frac\alpha\beta$",
            r"$\frac{\{a}{b}$",
            r"$\frac{{a}}{b}$",
            r"$\frac\%\%$",
            r"$\frac a b$",
            r"$\frac\\$",
        )
    )

    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    assert [fact.parse_status for fact in snapshot.inline_math] == [
        "preserved",
        "unsupported",
        "unsupported",
        "unsupported",
        "preserved",
        "preserved",
        "preserved",
        "preserved",
        "preserved",
        "unsupported",
    ]


def test_math_host_rejects_required_argument_ending_in_lone_backslash() -> None:
    body = "\\frac\\"
    source = f"{{math}}`{body}`"

    snapshot = _classify(MySTFrontend().lower((doc(source),)))

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        (body, "unsupported")
    ]
    [fact] = snapshot.inline_math
    assert fact.span is not None
    assert source[fact.span.start : fact.span.end] == body
    assert [(unknown.reason, unknown.excerpt) for unknown in snapshot.unknown_math] == [
        ("unsupported_syntax", body)
    ]


class _CountingText(str):
    accesses: int

    @overload
    def __getitem__(self, key: SupportsIndex, /) -> str: ...

    @overload
    def __getitem__(self, key: slice, /) -> str: ...

    def __getitem__(self, key: SupportsIndex | slice, /) -> str:
        self.accesses += 1
        return super().__getitem__(key)


def test_plain_text_candidate_scan_has_linear_work_without_a_relation() -> None:
    from scieqlint.frontend.myst_math import _plain_text_math_candidate_spans

    body = _CountingText("a+" * 2_048 + "a")
    body.accesses = 0

    assert tuple(_plain_text_math_candidate_spans(body)) == ()
    assert len(body) <= body.accesses <= 10 * len(body) + 10


def test_required_arity_validation_has_linear_index_work_for_nested_arguments() -> None:
    from scieqlint.parse.math import _has_missing_required_argument

    depth = 128
    nested = "1"
    for _ in range(depth):
        nested = rf"\frac{{{nested}}}{{1}}"
    body = _CountingText(nested)
    body.accesses = 0

    assert not _has_missing_required_argument(body)
    assert body.accesses <= len(body) + 10 * depth


def test_math_host_does_not_apply_required_arity_to_escaped_commands() -> None:
    body = r"\\frac{1}"

    snapshot = _classify(MySTFrontend().lower((doc(f"Inline ${body}$"),)))

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        (body, "preserved")
    ]
    assert snapshot.unknown_math == ()


def test_without_tex_comments_preserves_offsets_and_escaped_percent() -> None:
    from scieqlint.markdown import without_tex_comments

    source = "x% hidden\n\\% active"

    masked = without_tex_comments(source)

    assert len(masked) == len(source)
    assert masked[:2] == "x "
    assert masked[masked.index("\\%") :] == r"\% active"
