from __future__ import annotations

import json
from pathlib import PurePosixPath

import pytest

from scieqlint.app import check_documents
from scieqlint.config.model import Config, ProfileConfig
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument, SourceOrigin
from scieqlint.report.json import JsonReporter


def doc(text: str, *, origin: SourceOrigin | None = None) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("generated.md"),
        text,
        DocumentKind.MARKDOWN,
        origin=origin,
    )


def placeholder_facts(text: str):
    return tuple(
        fact
        for fact in MySTFrontend().lower((doc(text),)).generated_formulas
        if fact.placeholder_kind is not None
    )


def test_formula_placeholder_facts_cover_marker_empty_display_and_formula_image() -> None:
    source = """\
<!-- formula-not-decoded -->

$formula-not-decoded$

$$   $$

$$$$

![formula](assets/equation-placeholder.svg)
"""

    facts = placeholder_facts(source)

    assert [fact.kind for fact in facts] == [
        "placeholder",
        "placeholder",
        "empty-display",
        "empty-display",
        "image-placeholder",
    ]
    assert [fact.placeholder_kind for fact in facts] == [
        "formula-not-decoded",
        "formula-not-decoded",
        "empty-display-math",
        "empty-display-math",
        "formula-image",
    ]
    assert [source[fact.span.start : fact.span.end] for fact in facts if fact.span] == [
        "<!-- formula-not-decoded -->",
        "formula-not-decoded",
        "$$   $$",
        "$$$$",
        "![formula](assets/equation-placeholder.svg)",
    ]


def test_placeholder_scanner_rejects_prose_code_nonempty_math_and_nonformula_images() -> None:
    source = """\
The formula-not-decoded marker is discussed in prose.

`formula-not-decoded`

```text
formula-not-decoded
$$$$
![formula](formula.png)
```

$$x = 1$$

![plot of an equation](equation-of-state.png)

Text ![formula](formula.png) is not a standalone formula position.
"""

    assert placeholder_facts(source) == ()


def test_empty_display_detection_reuses_math_container_ownership() -> None:
    source = """\
```text
$$   $$
```

<!--
$$   $$
-->

$$   $$
"""

    facts = placeholder_facts(source)

    assert len(facts) == 1
    assert facts[0].span is not None
    assert source[facts[0].span.start : facts[0].span.end] == "$$   $$"


@pytest.mark.parametrize(
    "source",
    [
        "<!--\n$$$$\n-->\n",
        "<div>\n$$$$\n</div>\n",
        "    $$$$\n",
    ],
    ids=("html-comment", "raw-html", "indented-code"),
)
def test_empty_display_marker_respects_opaque_markdown_ownership(source: str) -> None:
    assert placeholder_facts(source) == ()


def test_generated_profile_json_preserves_span_and_placeholder_kind() -> None:
    source = "Before.\n\n![equation](equation.svg)\n"
    result = check_documents(
        (
            doc(
                source,
                origin=SourceOrigin(source_document_id="source/formulas.xml"),
            ),
        ),
        config=Config(
            profile=ProfileConfig(
                name="generated-myst",
                source_kind="jats-xml",
                conversion_stage="xml-to-markdown",
            )
        ),
    )
    diagnostics = tuple(
        diagnostic for diagnostic in result.diagnostics if diagnostic.code == "GEN004"
    )

    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.span is not None
    assert (diagnostic.span.line, diagnostic.span.col) == (3, 1)
    assert dict(diagnostic.properties) == {
        "formula_artifact_kind": "image-placeholder",
        "placeholder_kind": "formula-image",
        "generated_document": "generated.md",
        "source_document": "source/formulas.xml",
        "source_kind": "jats-xml",
        "conversion_stage": "xml-to-markdown",
    }

    payload = json.loads(JsonReporter().render(result))
    generated = next(item for item in payload["diagnostics"] if item["code"] == "GEN004")
    assert (generated["path"], generated["line"], generated["col"]) == (
        "generated.md",
        3,
        1,
    )
    assert generated["properties"]["placeholder_kind"] == "formula-image"


def test_default_profile_keeps_formula_placeholder_diagnostics_disabled() -> None:
    result = check_documents((doc("<!-- formula-not-decoded -->\n"),), config=Config())

    assert all(diagnostic.code != "GEN004" for diagnostic in result.diagnostics)


def test_placeholder_facts_are_deterministic_after_newline_normalization() -> None:
    lf = placeholder_facts("<!-- formula-not-decoded -->\n$$   $$\n")
    crlf = placeholder_facts("<!-- formula-not-decoded -->\r\n$$   $$\r\n")

    assert lf == crlf
