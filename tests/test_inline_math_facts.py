from __future__ import annotations

from pathlib import Path, PurePosixPath

from scieqlint.facts.math import InlineMathFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.frontend.myst_math import _merge_occupied
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.parse.math import MathHost


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


def test_math_host_keeps_ordinary_prose_out_of_plain_text_math() -> None:
    snapshot = MathHost().classify(
        MySTFrontend().lower((doc("Version 1 < 2; Status = complete; A>=B; a = b+c."),))
    )

    assert [(fact.body, fact.parse_status) for fact in snapshot.inline_math] == [
        ("1 < 2", "preserved"),
        ("Status = complete", "preserved"),
        ("A>=B", "text-leak"),
        ("a = b+c", "text-leak"),
    ]


def test_math_host_owns_plain_text_candidate_classification() -> None:
    lowered = MySTFrontend().lower((doc("compact a = b+c."),))

    assert [(fact.body, fact.parse_status) for fact in lowered.inline_math] == [
        ("a = b+c", "preserved"),
    ]
    classified = MathHost().classify(lowered)
    assert [(fact.body, fact.parse_status) for fact in classified.inline_math] == [
        ("a = b+c", "text-leak"),
    ]


def test_math_host_rejects_plain_prose_and_mismatched_delimiters() -> None:
    prose = InlineMathFact(
        fact_id="prose",
        document_id="generated.md",
        span=None,
        raw="ordinary prose",
        body="ordinary prose",
        delimiter_kind="plain-text",
        context="paragraph",
    )
    mismatched = InlineMathFact(
        fact_id="mismatched",
        document_id="generated.md",
        span=None,
        raw="(x]",
        body="(x]",
        delimiter_kind="dollar",
        context="paragraph",
    )

    snapshot = MathHost().classify(FactSnapshot(inline_math=(prose, mismatched)))

    assert [fact.parse_status for fact in snapshot.inline_math] == [
        "preserved",
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
    assert _merge_occupied(((4, 4), (8, 10), (9, 12), (20, 19))) == ((8, 12),)
