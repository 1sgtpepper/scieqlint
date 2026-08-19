from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.app import check_documents
from scieqlint.config.model import Config, ProfileConfig
from scieqlint.frontend.generated import _merge_ranges
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


def bracketed_facts(text: str):
    return tuple(
        fact
        for fact in MathHost().classify(MySTFrontend().lower((doc(text),))).generated_formulas
        if fact.kind == "bracketed-block"
    )


def test_bracketed_latex_blocks_preserve_complete_same_line_and_eof_spans() -> None:
    source = "Intro.\n\\[\nx = y\n\\]\n\\[ z = 1 \\]\n\\[\nunterminated"

    facts = bracketed_facts(source)

    assert [fact.complete for fact in facts] == [True, True, False]
    assert [source[fact.span.start : fact.span.end] for fact in facts if fact.span] == [
        "\\[\nx = y\n\\]",
        "\\[ z = 1 \\]",
        "\\[\nunterminated",
    ]
    assert [fact.text for fact in facts] == [
        "\\[\nx = y\n\\]",
        "\\[ z = 1 \\]",
        "\\[\nunterminated",
    ]


def test_bracketed_scanner_excludes_owned_math_code_inline_and_nonstandalone_text() -> None:
    source = """\
Text \\[ x = y \\] stays prose.

`\\[`

```text
\\[
x = y
\\]
```

$$
\\[
x = y
\\]
$$

\\\\[
not an opener
\\\\]
"""

    assert bracketed_facts(source) == ()


def test_nested_openers_have_one_owner_and_close_at_the_first_standalone_closer() -> None:
    source = "\\[\nouter\n\\[\ninner\n\\]\nafter\n\\]\n"

    facts = bracketed_facts(source)

    assert len(facts) == 1
    assert facts[0].complete is True
    assert facts[0].span is not None
    assert source[facts[0].span.start : facts[0].span.end] == "\\[\nouter\n\\[\ninner\n\\]"


def test_generated_profile_emits_complete_and_eof_diagnostics_in_source_order() -> None:
    source = "\\[\nx = y\n\\]\n\n\\[\nunterminated"

    result = check_documents(
        (
            doc(
                source,
                origin=SourceOrigin(source_document_id="source/formulas.tex"),
            ),
        ),
        config=Config(profile=ProfileConfig(name="generated-myst")),
    )
    diagnostics = tuple(
        diagnostic for diagnostic in result.diagnostics if diagnostic.code == "GEN003"
    )

    assert [diagnostic.detail for diagnostic in diagnostics] == [
        "standalone \\[...\\] display delimiters are not portable generated Markdown",
        "standalone \\[ display opener is not closed before end of file",
    ]
    assert [dict(diagnostic.properties)["complete"] for diagnostic in diagnostics] == [
        "true",
        "false",
    ]
    assert all(
        diagnostic.provenance_ids == ("generated.md::generated-provenance",)
        for diagnostic in diagnostics
    )


def test_default_profile_does_not_emit_bracketed_generated_diagnostic() -> None:
    result = check_documents((doc("\\[\nx=y\n\\]\n"),), config=Config())

    assert all(diagnostic.code != "GEN003" for diagnostic in result.diagnostics)


def test_bracketed_scanner_merges_overlapping_ranges_and_discards_empty_ranges() -> None:
    assert _merge_ranges(((4, 4), (8, 10), (9, 12), (20, 19))) == ((8, 12),)
