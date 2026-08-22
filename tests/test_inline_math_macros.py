from __future__ import annotations

import json
from pathlib import PurePosixPath

import pytest

from scieqlint.app import _profile_snapshot
from scieqlint.config.model import Config, ProfileConfig
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.parse.macros import scan_inline_macro_syntax
from scieqlint.parse.math import MathHost
from scieqlint.query.host import QueryHost


def doc(text: str, path: str = "macros.md") -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def lower(documents: tuple[SourceDocument, ...]) -> FactSnapshot:
    return MathHost().classify(MySTFrontend().lower(documents))


def test_macro_facts_are_snapshot_only_until_query_projection() -> None:
    snapshot = lower((doc(r"$\newcommand{\x}{x}$ $\x$"),))
    query = QueryHost(snapshot)

    # This slice deliberately records macro facts without adding a query or
    # diagnostic consumer. Existing math views must remain unchanged.
    assert snapshot.math_macro_declarations
    assert snapshot.math_macro_uses
    assert query.math.inline_math() == snapshot.inline_math
    assert query.math.unknown_math() == snapshot.unknown_math
    assert all("macro" not in name for name in dir(query.math))


def test_macro_facts_preserve_document_order_scope_and_exact_name_spans() -> None:
    source = (
        r"Before $\RR$. Define $\newcommand{\RR}{\mathbb{R}}$. "
        r"After $\RR$."
    )

    snapshot = lower((doc(source),))

    declaration = snapshot.math_macro_declarations[0]
    before, after = snapshot.math_macro_uses
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
    assert [use for use in snapshot.math_macro_uses if use.active_declaration_fact_id is None] == [
        before
    ]
    declarations_by_id = {item.fact_id: item for item in snapshot.math_macro_declarations}
    assert before.active_declaration_fact_id not in declarations_by_id
    assert declarations_by_id[after.active_declaration_fact_id] == declaration
    assert all(use.span is not None for use in (before, after))
    assert [source[use.span.start : use.span.end] for use in (before, after)] == [
        r"\RR",
        r"\RR",
    ]


def test_notebook_markdown_cells_preserve_macro_scope_and_encoded_source_spans() -> None:
    payload = {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": r"Before $\R$."},
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": r"Define $\newcommand{\R}{\mathbb{R}}$.",
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": r"Literal $\\newcommand{\literal}{x}$. After $\R$.",
            },
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    document = SourceDocument.from_text(
        PurePosixPath("macros.ipynb"),
        json.dumps(payload, sort_keys=True),
        DocumentKind.NOTEBOOK,
    )

    snapshot = _profile_snapshot(
        (document,),
        Config(profile=ProfileConfig(name="notebook-crossrefs")),
    )

    [declaration] = snapshot.math_macro_declarations
    before, after = snapshot.math_macro_uses
    assert [fact.span.cell for fact in snapshot.inline_math if fact.span is not None] == [
        0,
        1,
        2,
        2,
    ]
    assert declaration.macro_name == r"\R"
    assert declaration.declaration_order == 0
    assert declaration.span is not None
    assert declaration.span.cell == 1
    assert before.span is not None
    assert before.span.cell == 0
    assert after.span is not None
    assert after.span.cell == 2
    assert before.active_declaration_fact_id is None
    assert after.active_declaration_fact_id == declaration.fact_id
    assert [
        json.loads(f'"{document.text[fact.span.start : fact.span.end]}"')
        for fact in (declaration, before, after)
        if fact.span is not None
    ] == [r"\R", r"\R", r"\R"]


def test_notebook_source_list_boundaries_preserve_exact_macro_segments() -> None:
    payload = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "Define $\\newcommand{\\",
                    "RR}{\\mathbb{R}}$. Use $\\R",
                    "R$.\r\n",
                ],
            }
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    document = SourceDocument.from_text(
        PurePosixPath("macro-segments.ipynb"),
        json.dumps(payload, sort_keys=True),
        DocumentKind.NOTEBOOK,
    )

    snapshot = _profile_snapshot(
        (document,),
        Config(profile=ProfileConfig(name="notebook-crossrefs")),
    )

    [declaration] = snapshot.math_macro_declarations
    [use] = snapshot.math_macro_uses
    for fact in (declaration, use):
        assert fact.span is not None
        assert fact.span.cell == 0
        assert fact.span.cell_line == 1
        assert len(fact.span.segments) == len(r"\RR")
        assert (
            "".join(
                json.loads(f'"{document.text[start:end]}"')
                for segment in fact.span.segments
                for start, end in segment.ranges
            )
            == r"\RR"
        )


def test_redeclaration_changes_only_later_use_context() -> None:
    source = (
        r"$\newcommand{\v}[1]{#1}$ $\v{x}$ "
        r"$\renewcommand{\v}[1]{\mathbf{#1}}$ $\v{y}$"
    )

    snapshot = lower((doc(source),))
    first, second = snapshot.math_macro_declarations
    first_use, second_use = snapshot.math_macro_uses

    assert [fact.declaration_order for fact in (first, second)] == [0, 1]
    assert [fact.declaration_kind for fact in (first, second)] == [
        "newcommand",
        "renewcommand",
    ]
    assert first_use.active_declaration_fact_id == first.fact_id
    assert second_use.active_declaration_fact_id == second.fact_id


def test_providecommand_does_not_replace_an_active_macro_declaration() -> None:
    source = r"$\newcommand{\x}{old}$ $\providecommand{\x}{new}$ $\x$"

    snapshot = lower((doc(source),))
    first, provided = snapshot.math_macro_declarations
    [use] = snapshot.math_macro_uses

    assert [fact.declaration_kind for fact in (first, provided)] == [
        "newcommand",
        "providecommand",
    ]
    assert [fact.replacement for fact in (first, provided)] == ["old", "new"]
    assert use.active_declaration_fact_id == first.fact_id


def test_common_newcommand_providecommand_and_def_forms_are_finite() -> None:
    source = " ".join(
        (
            r"$\newcommand*\scalar{a_{b_{c}}}$",
            r"$\providecommand{\unit}[2][m]{#1\,#2}$",
            r"$\def \pair #1#2{(#1,#2)}$",
        )
    )

    declarations = lower((doc(source),)).math_macro_declarations

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

    snapshot = lower((doc(source),))

    declaration = snapshot.math_macro_declarations[0]
    use = snapshot.math_macro_uses[0]
    assert declaration.macro_name == r"\A"
    assert use.active_declaration_fact_id == declaration.fact_id


def test_macro_declarations_and_uses_inside_tex_comments_are_ignored() -> None:
    body = (
        r"\newcommand{\active}{1} \active "
        r"% \newcommand{\commented}{2} \commented"
    )
    source = f"{{math}}`{body}`"

    syntax = scan_inline_macro_syntax(body)
    snapshot = lower((doc(source),))

    assert [item.name for item in syntax.declarations] == [r"\active"]
    assert [item.name for item in syntax.uses] == [r"\active"]
    assert [item.macro_name for item in snapshot.math_macro_declarations] == [r"\active"]
    assert [item.macro_name for item in snapshot.math_macro_uses] == [r"\active"]
    (declaration,) = snapshot.math_macro_declarations
    (use,) = snapshot.math_macro_uses
    assert declaration.replacement == "1"
    assert source[declaration.span.start : declaration.span.end] == r"\active"
    assert source[use.span.start : use.span.end] == r"\active"


def test_macro_context_is_document_scoped_and_input_order_independent() -> None:
    a = doc(r"$\newcommand{\same}{A}$ $\same$", "a.md")
    b = doc(r"$\same$ $\newcommand{\same}{B}$", "b.md")

    forward = lower((b, a))
    reverse = lower((a, b))

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
            r"Whitespace-delimited def $\def\spaced#1 #2{#1#2}$.",
            r"Unsupported $\DeclareMathOperator{\rank}{rank}$.",
            r"Ordinary prose \newcommand{\prose}{x} is not inline math.",
            r"`$\newcommand{\code}{x}$`",
            r"$$\newcommand{\display}{x}$$",
        )
    )

    snapshot = lower((doc(source),))

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


def test_parser_rejects_crossing_delimiters_without_promoting_the_use() -> None:
    syntax = scan_inline_macro_syntax(r"\newcommand{\x}[1][d}{a] {b} \x")

    assert syntax.declarations == ()
    assert syntax.uses == ()


def test_parser_preserves_legal_mixed_delimiter_nesting() -> None:
    syntax = scan_inline_macro_syntax(r"\newcommand{\x}[1][d{e}]{a[b]} \x")

    assert [
        (item.name, item.parameter_count, item.replacement) for item in syntax.declarations
    ] == [(r"\x", 1, "a[b]")]
    assert [(item.name, item.start) for item in syntax.uses] == [(r"\x", 31)]


def test_crossing_malformed_recovery_preserves_later_declarations() -> None:
    syntax = scan_inline_macro_syntax(
        r"\newcommand{\bad}[1][x{y]z}] "
        r"\newcommand{\later}{z} \later"
    )

    assert [(item.name, item.replacement) for item in syntax.declarations] == [
        (r"\later", "z"),
    ]
    assert [item.name for item in syntax.uses] == [r"\later"]


def test_crossing_recovery_keeps_nested_commands_opaque_until_boundary() -> None:
    syntax = scan_inline_macro_syntax(
        r"\newcommand{\bad}{x] \newcommand{\inner}{x}} "
        r"\newcommand{\later}{z} \later"
    )

    assert [(item.name, item.replacement) for item in syntax.declarations] == [
        (r"\later", "z"),
    ]
    assert [item.name for item in syntax.uses] == [r"\later"]


def test_symmetric_crossing_recovery_keeps_nested_commands_opaque_until_boundary() -> None:
    syntax = scan_inline_macro_syntax(
        r"\newcommand{\bad}[1][x{y] \newcommand{\inner}{x}} "
        r"\newcommand{\later}{z} \later"
    )

    assert [(item.name, item.replacement) for item in syntax.declarations] == [
        (r"\later", "z"),
    ]
    assert [item.name for item in syntax.uses] == [r"\later"]


def test_unclosed_crossing_recovery_keeps_nested_commands_opaque_to_eof() -> None:
    syntax = scan_inline_macro_syntax(r"\newcommand{\bad}{x] \newcommand{\inner}{x}")

    assert syntax.declarations == ()
    assert syntax.uses == ()


def test_malformed_declaration_does_not_promote_nested_commands_or_uses() -> None:
    syntax = scan_inline_macro_syntax(r"\newcommand{\bad}{\newcommand{\inner}{x}")

    assert syntax.declarations == ()
    assert syntax.uses == ()


def test_malformed_declaration_recovery_preserves_later_declarations() -> None:
    syntax = scan_inline_macro_syntax(
        r"\newcommand{\bad}[ab]{\newcommand{\inner}{x}} "
        r"\newcommand{\later}{z} \later"
    )

    assert [(item.name, item.replacement) for item in syntax.declarations] == [
        (r"\later", "z"),
    ]
    assert [item.name for item in syntax.uses] == [r"\later"]


def test_repeated_unclosed_declarations_remain_bounded_and_opaque() -> None:
    source = " ".join(r"\newcommand{\bad" for _ in range(64))

    syntax = scan_inline_macro_syntax(source)

    assert syntax.declarations == ()
    assert syntax.uses == ()


def test_parser_handles_whitespace_escaped_groups_and_later_uses() -> None:
    syntax = scan_inline_macro_syntax(r"  \newcommand  { \x   }  {\{x\}}  \x  ")

    assert [(item.name, item.replacement) for item in syntax.declarations] == [
        (r"\x", r"\{x\}"),
    ]
    assert [(item.name, item.start) for item in syntax.uses] == [(r"\x", 34)]


def test_macro_commands_inside_declaration_replacements_are_not_use_sites() -> None:
    source = (
        r"$\newcommand{\base}{x}$ "
        r"$\newcommand{\derived}{\base + 1}$ "
        r"$\derived + \base$"
    )

    snapshot = lower((doc(source),))

    assert [use.macro_name for use in snapshot.math_macro_uses] == [
        r"\derived",
        r"\base",
    ]


def test_macro_facts_are_stable_across_newline_normalization_and_eof() -> None:
    lf = lower((doc(r"$\newcommand{\x}{1}$" + "\n"),))
    crlf = lower((doc(r"$\newcommand{\x}{1}$" + "\r\n"),))
    eof = lower((doc(r"$\newcommand{\x}{1}$"),))

    assert lf.math_macro_declarations == crlf.math_macro_declarations
    assert eof.math_macro_declarations[0].raw == r"\newcommand{\x}{1}"


def test_macro_facts_preserve_active_declaration_across_many_inline_facts() -> None:
    source = " ".join([r"$\newcommand{\x}{1}$"] + [r"$\x$" for _ in range(256)])

    snapshot = lower((doc(source),))

    assert len(snapshot.math_macro_declarations) == 1
    assert len(snapshot.math_macro_uses) == 256
    assert {use.active_declaration_fact_id for use in snapshot.math_macro_uses} == {
        snapshot.math_macro_declarations[0].fact_id
    }


def test_math_host_rejects_nested_declaration_after_crossing_closer() -> None:
    source = (
        r"$\newcommand{\bad}{x] \newcommand{\inner}{x}}$ "
        r"$\newcommand{\later}{z}$ $\later$"
    )

    snapshot = lower((doc(source),))

    assert [fact.macro_name for fact in snapshot.math_macro_declarations] == [r"\later"]
    [use] = snapshot.math_macro_uses
    assert use.macro_name == r"\later"
    declaration = snapshot.math_macro_declarations[0]
    assert use.active_declaration_fact_id == declaration.fact_id
    assert declaration.span is not None
    assert source[declaration.span.start : declaration.span.end] == r"\later"


def test_math_host_keeps_unclosed_crossing_nested_declaration_opaque() -> None:
    source = (
        r"$\newcommand{\bad}{x] \newcommand{\inner}{x}$ "
        r"$\newcommand{\later}{z}$ $\later$"
    )

    snapshot = lower((doc(source),))

    assert [fact.macro_name for fact in snapshot.math_macro_declarations] == [r"\later"]
    [use] = snapshot.math_macro_uses
    assert use.macro_name == r"\later"
    declaration = snapshot.math_macro_declarations[0]
    assert use.active_declaration_fact_id == declaration.fact_id


def test_math_host_rejects_nested_declaration_after_symmetric_crossing_closer() -> None:
    source = (
        r"$\newcommand{\bad}[1][x{y] \newcommand{\inner}{x}}$ "
        r"$\newcommand{\later}{z}$ $\later$"
    )

    snapshot = lower((doc(source),))

    assert [fact.macro_name for fact in snapshot.math_macro_declarations] == [r"\later"]
    [use] = snapshot.math_macro_uses
    assert use.macro_name == r"\later"
    declaration = snapshot.math_macro_declarations[0]
    assert use.active_declaration_fact_id == declaration.fact_id


def test_top_level_unmatched_closer_does_not_hide_later_macro_facts() -> None:
    snapshot = lower((doc(r"$] \newcommand{\x}{x} \x$"),))

    [declaration] = snapshot.math_macro_declarations
    [use] = snapshot.math_macro_uses
    assert (declaration.macro_name, declaration.replacement) == (r"\x", "x")
    assert use.macro_name == r"\x"
    assert use.active_declaration_fact_id == declaration.fact_id
