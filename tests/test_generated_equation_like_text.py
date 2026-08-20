from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.app import check_documents
from scieqlint.config.model import Config, ProfileConfig
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument, SourceOrigin
from scieqlint.parse.math import MathHost
from scieqlint.schema import SchemaHost


def doc(text: str, *, origin: SourceOrigin | None = None) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("generated.md"),
        text,
        DocumentKind.MARKDOWN,
        origin=origin,
    )


def equation_text_facts(text: str):
    return tuple(
        fact
        for fact in MathHost().classify(MySTFrontend().lower((doc(text),))).generated_formulas
        if fact.kind == "equation-like-text"
    )


def test_equation_like_text_facts_cover_isolated_paragraph_list_and_blockquote_items() -> None:
    source = """\
x = y

- E = mc^2
- velocity = distance / time

> a = b+c

F(x) = x + 1
"""

    facts = equation_text_facts(source)

    assert [fact.text for fact in facts] == [
        "x = y",
        "E = mc^2",
        "velocity = distance / time",
        "a = b+c",
        "F(x) = x + 1",
    ]
    assert [source[fact.span.start : fact.span.end] for fact in facts if fact.span] == [
        fact.text for fact in facts
    ]
    assert all(fact.source_math_fact_id is not None for fact in facts)


def test_equation_substrings_and_ordinary_symbolic_prose_are_negative_controls() -> None:
    source = """\
The result is x = y.

Status = complete

This paragraph starts with prose.
x = y
and continues after the equation.

Temperature > threshold
"""

    assert equation_text_facts(source) == ()


def test_equation_text_classifier_excludes_math_code_links_brackets_and_heading_roles() -> None:
    source = """\
# x = y

$x = y$

$$
x = y
$$

\\[
x = y
\\]

`x = y`

```text
x = y
```

[x = y](#target)
"""

    assert equation_text_facts(source) == ()


def test_list_continuation_prevents_false_standalone_item_but_adjacent_items_remain_valid() -> None:
    source = """\
- x = y
  where x and y are labels

- a = b
- c = d
"""

    facts = equation_text_facts(source)

    assert [fact.text for fact in facts] == ["a = b", "c = d"]


def test_lazy_blockquote_continuation_is_not_an_equation_item_but_an_interrupted_quote_is() -> None:
    lazy = equation_text_facts("> explanatory prose\nF(x) = x + 1\n")
    interrupted = equation_text_facts("> explanatory prose\n\n> F(x) = x + 1\n")

    assert lazy == ()
    assert [fact.text for fact in interrupted] == ["F(x) = x + 1"]


def test_generated_profile_emits_stable_equation_text_diagnostic_and_provenance() -> None:
    source = "Intro.\n\nF(x) = x + 1\n"

    result = check_documents(
        (
            doc(
                source,
                origin=SourceOrigin(source_document_id="source/formulas.pdf"),
            ),
        ),
        config=Config(
            profile=ProfileConfig(
                name="generated-myst",
                source_kind="pdf",
                conversion_stage="text-to-markdown",
            )
        ),
    )
    diagnostics = tuple(
        diagnostic for diagnostic in result.diagnostics if diagnostic.code == "GEN005"
    )

    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.message == "standalone text block looks like an equation"
    assert diagnostic.detail == (
        "equation-like text was emitted outside a math container: 'F(x) = x + 1'"
    )
    assert diagnostic.span is not None
    assert (diagnostic.span.line, diagnostic.span.col) == (3, 1)
    projection = SchemaHost.project_diagnostic(diagnostic)
    assert projection.provenance_ids == ("generated.md::generated-provenance",)
    assert dict(projection.properties) == {
        "formula_artifact_kind": "equation-like-text",
        "generated_document": "generated.md",
        "source_document": "source/formulas.pdf",
        "source_kind": "pdf",
        "conversion_stage": "text-to-markdown",
    }


def test_default_profile_keeps_equation_text_diagnostics_disabled() -> None:
    result = check_documents((doc("x = y\n"),), config=Config())

    assert all(diagnostic.code != "GEN005" for diagnostic in result.diagnostics)


def test_equation_text_facts_are_deterministic_after_newline_normalization() -> None:
    assert equation_text_facts("x = y\n") == equation_text_facts("x = y\r\n")


def test_equation_text_classifier_uses_source_roles_and_one_based_spans() -> None:
    source = "- x = y\n\n> a = b+c\n"

    facts = equation_text_facts(source)

    assert [(fact.text, fact.span.line, fact.span.col) for fact in facts if fact.span] == [
        ("x = y", 1, 3),
        ("a = b+c", 3, 3),
    ]
    assert [source[fact.span.start : fact.span.end] for fact in facts if fact.span] == [
        fact.text for fact in facts
    ]
