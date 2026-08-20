from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.parse.math import MathHost
from scieqlint.query.host import QueryHost


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath("generated.md"), text, DocumentKind.MARKDOWN)


def test_inline_math_facts_preserve_delimiters_roles_status_and_exact_spans() -> None:
    source = (Path(__file__).parent / "fixtures" / "generated" / "inline_math_facts.md").read_text(
        encoding="utf-8"
    )

    snapshot = MathHost().classify(MySTFrontend().lower((doc(source),)))

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


def test_math_host_classifies_malformed_and_unsupported_inline_math() -> None:
    snapshot = MathHost().classify(
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


@pytest.mark.public_regression
@pytest.mark.parametrize(
    "command",
    [r"\frac", r"\dfrac", r"\tfrac", r"\binom"],
    ids=["frac", "dfrac", "tfrac", "binom"],
)
def test_math_host_rejects_bare_required_arity_commands(command: str) -> None:
    source = f"Inline ${command}$"
    snapshot = MathHost().classify(MySTFrontend().lower((doc(source),)))

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        (command, "unsupported")
    ]
    [fact] = snapshot.inline_math
    assert fact.span is not None
    assert source[fact.span.start : fact.span.end] == command
    assert [(fact.reason, fact.excerpt) for fact in snapshot.unknown_math] == [
        ("unsupported_syntax", command)
    ]


@pytest.mark.public_regression
def test_math_host_rejects_required_arity_command_with_one_control_sequence_argument() -> None:
    body = r"\frac\alpha"
    snapshot = MathHost().classify(MySTFrontend().lower((doc(f"Inline ${body}$"),)))

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        (body, "unsupported")
    ]
    assert [(fact.reason, fact.excerpt) for fact in snapshot.unknown_math] == [
        ("unsupported_syntax", body)
    ]


@pytest.mark.parametrize(
    "body",
    [
        "\\frac{1}% the second argument is absent",
        "\\frac% both arguments are absent",
    ],
    ids=["missing-second-after-comment", "missing-first-after-comment"],
)
def test_math_host_does_not_treat_tex_comments_as_required_arguments(body: str) -> None:
    snapshot = MathHost().classify(MySTFrontend().lower((doc(f"Inline ${body}$"),)))

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        (body, "unsupported")
    ]
    assert [(fact.reason, fact.excerpt) for fact in snapshot.unknown_math] == [
        ("unsupported_syntax", body)
    ]


@pytest.mark.parametrize(
    "body",
    [
        r"\frac{1}{2}",
        r"\dfrac{x}{y}",
        r"\tfrac{a}{b}",
        r"\binom{n}{k}",
        r"\frac\alpha\beta",
    ],
    ids=["frac", "dfrac", "tfrac", "binom", "control-sequences"],
)
def test_math_host_preserves_required_arity_commands_with_arguments(body: str) -> None:
    snapshot = MathHost().classify(MySTFrontend().lower((doc(f"Inline ${body}$"),)))

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        (body, "preserved")
    ]
    assert snapshot.unknown_math == ()


def test_math_host_keeps_ordinary_prose_out_of_plain_text_math() -> None:
    snapshot = MathHost().classify(
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


def test_math_host_owns_plain_text_candidate_classification() -> None:
    lowered = MySTFrontend().lower((doc("compact a = b+c."),))

    assert [(fact.body, fact.parse_status) for fact in lowered.inline_math] == [
        ("a = b+c", "candidate"),
    ]
    classified = MathHost().classify(lowered)
    assert [(fact.body, fact.parse_status) for fact in classified.inline_math] == [
        ("a = b+c", "text-leak"),
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


def test_inline_math_facts_are_deterministic_across_newline_normalization() -> None:
    lf = MySTFrontend().lower((doc("Text $x = 1$.\n"),))
    crlf = MySTFrontend().lower((doc("Text $x = 1$.\r\n"),))

    assert lf.inline_math == crlf.inline_math


def test_empty_delimited_math_is_ignored_but_nonempty_math_is_preserved() -> None:
    snapshot = MySTFrontend().lower((doc(r"Empty \(\) and \(x = 1\)."),))

    assert [(fact.delimiter_kind, fact.body) for fact in snapshot.inline_math] == [
        ("latex-paren", "x = 1"),
    ]


def test_inline_math_range_merge_discards_empty_ranges_and_merges_overlaps() -> None:
    from scieqlint.frontend.myst_math import _merge_occupied

    assert _merge_occupied(((4, 4), (8, 10), (9, 12), (20, 19))) == ((8, 12),)
