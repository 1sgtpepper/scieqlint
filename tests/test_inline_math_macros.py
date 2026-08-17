from __future__ import annotations

from dataclasses import replace
from pathlib import PurePosixPath

import pytest

from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.math_macros import inline_math_macro_facts
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.parse.macros import scan_inline_macro_syntax
from scieqlint.query.host import QueryHost


def doc(text: str, path: str = "macros.md") -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def test_macro_facts_preserve_document_order_scope_and_exact_name_spans() -> None:
    source = (
        r"Before $\RR$. Define $\newcommand{\RR}{\mathbb{R}}$. "
        r"After $\RR$."
    )

    snapshot = MySTFrontend().lower((doc(source),))
    query = QueryHost(snapshot)

    declaration = query.math.macro_declarations()[0]
    before, after = query.math.macro_uses()
    assert declaration.macro_name == r"\RR"
    assert declaration.declaration_kind == "newcommand"
    assert declaration.parameter_count == 0
    assert declaration.replacement == r"\mathbb{R}"
    assert declaration.declaration_order == 0
    assert declaration.span is not None
    assert source[declaration.span.start : declaration.span.end] == r"\RR"
    assert declaration.raw == r"\newcommand{\RR}{\mathbb{R}}"

    assert before.active_declaration_fact_id is None
    assert after.active_declaration_fact_id == declaration.fact_id
    assert [use for use in query.math.macro_uses() if use.active_declaration_fact_id is None] == [
        before
    ]
    declarations_by_id = {item.fact_id: item for item in query.math.macro_declarations()}
    assert before.active_declaration_fact_id not in declarations_by_id
    assert declarations_by_id[after.active_declaration_fact_id] == declaration
    assert all(use.span is not None for use in (before, after))
    assert [source[use.span.start : use.span.end] for use in (before, after)] == [
        r"\RR",
        r"\RR",
    ]


def test_redeclaration_changes_only_later_use_context() -> None:
    source = (
        r"$\newcommand{\v}[1]{#1}$ $\v{x}$ "
        r"$\renewcommand{\v}[1]{\mathbf{#1}}$ $\v{y}$"
    )

    snapshot = MySTFrontend().lower((doc(source),))
    first, second = snapshot.math_macro_declarations
    first_use, second_use = snapshot.math_macro_uses

    assert [fact.declaration_order for fact in (first, second)] == [0, 1]
    assert [fact.declaration_kind for fact in (first, second)] == [
        "newcommand",
        "renewcommand",
    ]
    assert first_use.active_declaration_fact_id == first.fact_id
    assert second_use.active_declaration_fact_id == second.fact_id


def test_common_newcommand_providecommand_and_def_forms_are_finite() -> None:
    source = " ".join(
        (
            r"$\newcommand*\scalar{a_{b_{c}}}$",
            r"$\providecommand{\unit}[2][m]{#1\,#2}$",
            r"$\def\pair#1#2{(#1,#2)}$",
        )
    )

    declarations = MySTFrontend().lower((doc(source),)).math_macro_declarations

    assert [fact.macro_name for fact in declarations] == [
        r"\scalar",
        r"\unit",
        r"\pair",
    ]
    assert [fact.declaration_kind for fact in declarations] == [
        "newcommand",
        "providecommand",
        "def",
    ]
    assert [fact.parameter_count for fact in declarations] == [0, 2, 2]
    assert [fact.replacement for fact in declarations] == [
        "a_{b_{c}}",
        r"#1\,#2",
        "(#1,#2)",
    ]


def test_macro_facts_cover_myst_role_and_latex_parenthesis_inline_forms() -> None:
    source = r"{math}`\newcommand{\A}{a}` then \(\A + 1\)."

    snapshot = MySTFrontend().lower((doc(source),))

    declaration = snapshot.math_macro_declarations[0]
    use = snapshot.math_macro_uses[0]
    assert declaration.macro_name == r"\A"
    assert use.active_declaration_fact_id == declaration.fact_id


def test_macro_context_is_document_scoped_and_input_order_independent() -> None:
    a = doc(r"$\newcommand{\same}{A}$ $\same$", "a.md")
    b = doc(r"$\same$ $\newcommand{\same}{B}$", "b.md")

    forward = MySTFrontend().lower((b, a))
    reverse = MySTFrontend().lower((a, b))

    def contract(
        snapshot: FactSnapshot,
    ) -> tuple[tuple[object, ...], tuple[object, ...]]:
        return (
            tuple(
                (
                    fact.document_id,
                    fact.macro_name,
                    fact.replacement,
                    fact.declaration_order,
                )
                for fact in snapshot.math_macro_declarations
            ),
            tuple(
                (
                    fact.document_id,
                    fact.macro_name,
                    fact.active_declaration_fact_id,
                )
                for fact in snapshot.math_macro_uses
            ),
        )

    assert contract(forward) == contract(reverse)
    uses = {use.document_id: use for use in forward.math_macro_uses}
    declarations = {
        declaration.document_id: declaration for declaration in forward.math_macro_declarations
    }
    assert uses["a.md"].active_declaration_fact_id == declarations["a.md"].fact_id
    assert uses["b.md"].active_declaration_fact_id is None


def test_literal_malformed_and_unsupported_declarations_do_not_create_facts() -> None:
    source = "\n".join(
        (
            r"Literal $\\newcommand{\literal}{x}$.",
            r"Malformed $\newcommand{\broken}{x$.",
            r"Delimited def $\def\csv#1,{#1}$.",
            r"Unsupported $\DeclareMathOperator{\rank}{rank}$.",
            r"Ordinary prose \newcommand{\prose}{x} is not inline math.",
            r"`$\newcommand{\code}{x}$`",
            r"$$\newcommand{\display}{x}$$",
        )
    )

    snapshot = MySTFrontend().lower((doc(source),))

    assert snapshot.math_macro_declarations == ()
    assert snapshot.math_macro_uses == ()


@pytest.mark.parametrize(
    "body",
    [
        "\\",
        r"\newcommand{} {x}",
        r"\newcommand{\x}[",
        r"\newcommand{\x}[ab]{x}",
        r"\newcommand{\x}[0][d]{x}",
        r"\newcommand{\x}[1][",
        r"\def{x}",
        r"\def\x",
        r"\def\x#2{x}",
        r"\def\x#1{",
        r"\newcommand{",
        r"\newcommand{   }{x}",
        r"\newcommand{x}{x}",
        r"\newcommand{\x extra}{x}",
        r"\newcommand \%{x}",
        r"\newcommand{\x}x",
    ],
)
def test_parser_rejects_malformed_declarations_without_promoting_them(body: str) -> None:
    assert scan_inline_macro_syntax(body).declarations == ()


def test_parser_handles_whitespace_escaped_groups_and_later_uses() -> None:
    syntax = scan_inline_macro_syntax(r"  \newcommand  { \x   }  {\{x\}}  \x  ")

    assert [(item.name, item.replacement) for item in syntax.declarations] == [
        (r"\x", r"\{x\}"),
    ]
    assert [(item.name, item.start) for item in syntax.uses] == [(r"\x", 34)]


def test_stale_inline_math_facts_are_ignored_before_macro_lowering() -> None:
    source = doc(r"$\newcommand{\x}{1}$")
    snapshot = MySTFrontend().lower((source,))
    stale = replace(snapshot.inline_math[0], body=snapshot.inline_math[0].body + " stale")

    assert inline_math_macro_facts((source,), (stale,)) == ((), ())


def test_plain_text_math_facts_are_ignored_before_macro_lowering() -> None:
    source = doc(r"$\newcommand{\x}{1}$")
    snapshot = MySTFrontend().lower((source,))
    plain_text = replace(snapshot.inline_math[0], delimiter_kind="plain-text")

    assert inline_math_macro_facts((source,), (plain_text,)) == ((), ())


def test_macro_commands_inside_declaration_replacements_are_not_use_sites() -> None:
    source = (
        r"$\newcommand{\base}{x}$ "
        r"$\newcommand{\derived}{\base + 1}$ "
        r"$\derived + \base$"
    )

    snapshot = MySTFrontend().lower((doc(source),))

    assert [use.macro_name for use in snapshot.math_macro_uses] == [
        r"\derived",
        r"\base",
    ]


def test_macro_facts_are_stable_across_newline_normalization_and_eof() -> None:
    lf = MySTFrontend().lower((doc(r"$\newcommand{\x}{1}$" + "\n"),))
    crlf = MySTFrontend().lower((doc(r"$\newcommand{\x}{1}$" + "\r\n"),))
    eof = MySTFrontend().lower((doc(r"$\newcommand{\x}{1}$"),))

    assert lf.math_macro_declarations == crlf.math_macro_declarations
    assert eof.math_macro_declarations[0].raw == r"\newcommand{\x}{1}"


def test_macro_scanning_handles_many_inline_facts_without_cross_fact_rescans() -> None:
    source = " ".join([r"$\newcommand{\x}{1}$"] + [r"$\x$" for _ in range(256)])

    snapshot = MySTFrontend().lower((doc(source),))

    assert len(snapshot.math_macro_declarations) == 1
    assert len(snapshot.math_macro_uses) == 256
    assert {use.active_declaration_fact_id for use in snapshot.math_macro_uses} == {
        snapshot.math_macro_declarations[0].fact_id
    }
