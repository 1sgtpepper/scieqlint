from __future__ import annotations

from pathlib import Path, PurePosixPath

from scieqlint.api import check_documents
from scieqlint.config.model import Config, ProfileConfig
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument, SourceOrigin
from scieqlint.parse.math import MathHost
from scieqlint.query.host import QueryHost


def _fixture() -> tuple[str, SourceDocument]:
    source = (
        Path(__file__).parent / "fixtures" / "jats" / "inline_formula_converted.md"
    ).read_text(encoding="utf-8")
    document = SourceDocument.from_text(
        PurePosixPath("article.jats.md"),
        source,
        DocumentKind.MARKDOWN,
    )
    return source, document


def test_jats_converted_fixture_preserves_inline_formulas_across_content_layers() -> None:
    source, document = _fixture()

    frontend_snapshot = MySTFrontend().lower((document,))
    snapshot = MathHost().classify(frontend_snapshot)
    expected_bodies = [
        "E = mc^2",
        "x_i = y_i",
        "a_i + b_i = c_i",
        "p = q+r",
        "z = 3",
    ]
    raw_inline_math = snapshot.inline_math
    inline_math = QueryHost(snapshot).math.inline_math()

    assert [fact.body for fact in raw_inline_math] == expected_bodies
    assert [fact.parse_status for fact in raw_inline_math] == ["preserved"] * len(expected_bodies)
    assert [
        (fact.kind, fact.candidate_kind, fact.text, fact.source_math_fact_id)
        for fact in frontend_snapshot.generated_formulas
    ] == [
        ("candidate", "formula-text", body, math_fact.fact_id)
        for body, math_fact in zip(expected_bodies, raw_inline_math, strict=True)
    ]
    assert snapshot.generated_formulas == ()
    assert inline_math == raw_inline_math

    assert [fact.body for fact in inline_math] == expected_bodies
    assert [fact.delimiter_kind for fact in inline_math] == [
        "dollar",
        "dollar",
        "myst-role",
        "latex-paren",
        "dollar",
    ]
    assert [fact.surrounding_text_role for fact in inline_math] == [
        "paragraph",
        "list-item",
        "list-item",
        "list-item",
        "blockquote",
    ]
    assert all(fact.span is not None for fact in inline_math)
    assert [
        source[fact.span.start : fact.span.end] for fact in inline_math if fact.span is not None
    ] == [fact.body for fact in inline_math]


def test_jats_converted_fixture_keeps_literal_xml_in_code_inert() -> None:
    _source, document = _fixture()

    frontend_snapshot = MySTFrontend().lower((document,))
    snapshot = MathHost().classify(frontend_snapshot)
    inline_math = QueryHost(snapshot).math.inline_math()

    assert [fact.body for fact in snapshot.inline_math] == [
        "E = mc^2",
        "x_i = y_i",
        "a_i + b_i = c_i",
        "p = q+r",
        "z = 3",
    ]
    assert all("hidden" not in fact.body for fact in inline_math)
    assert all("hidden" not in fact.body for fact in snapshot.inline_math)
    assert all("hidden" not in fact.text for fact in frontend_snapshot.generated_formulas)
    assert snapshot.generated_formulas == ()
    assert [fact.info_string for fact in snapshot.fences] == ["text"]


def test_jats_conversion_origin_is_explicit_profile_metadata_not_inferred_from_path() -> None:
    generated_config = Config(
        profile=ProfileConfig(
            name="generated-myst",
            source_kind="jats-xml",
            conversion_stage="xml-to-markdown",
        )
    )
    document = SourceDocument.from_text(
        PurePosixPath("article.jats.md"),
        "<!-- formula-not-decoded -->\n",
        DocumentKind.MARKDOWN,
        origin=SourceOrigin(source_document_id="article.jats.xml"),
    )

    default = check_documents([document], config=Config())
    generated = check_documents([document], config=generated_config)
    path_only = SourceDocument.from_text(
        PurePosixPath("article.jats.md"),
        "<!-- formula-not-decoded -->\n",
        DocumentKind.MARKDOWN,
        origin=None,
    )
    path_only_generated = check_documents([path_only], config=generated_config)

    assert default.diagnostics == ()
    assert [(diagnostic.code, diagnostic.profile) for diagnostic in generated.diagnostics] == [
        ("GEN004", "generated-myst")
    ]
    assert dict(generated.diagnostics[0].properties) == {
        "conversion_stage": "xml-to-markdown",
        "formula_artifact_kind": "placeholder",
        "generated_document": "article.jats.md",
        "placeholder_kind": "formula-not-decoded",
        "source_document": "article.jats.xml",
        "source_kind": "jats-xml",
    }
    assert [
        (diagnostic.code, diagnostic.profile, diagnostic.provenance_ids, diagnostic.properties)
        for diagnostic in path_only_generated.diagnostics
    ] == [
        (
            "GEN004",
            "generated-myst",
            (),
            (
                ("formula_artifact_kind", "placeholder"),
                ("placeholder_kind", "formula-not-decoded"),
            ),
        )
    ]
