from __future__ import annotations

from pathlib import Path, PurePosixPath

from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath("generated.md"), text, DocumentKind.MARKDOWN)


def test_inline_math_facts_preserve_delimiters_roles_status_and_exact_spans() -> None:
    source = (Path(__file__).parent / "fixtures" / "generated" / "inline_math_facts.md").read_text(
        encoding="utf-8"
    )

    snapshot = MySTFrontend().lower((doc(source),))

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
