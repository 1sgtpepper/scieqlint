from dataclasses import FrozenInstanceError
from pathlib import PurePosixPath
from typing import Any

import pytest

from scieqlint.diag.ir import DiagnosticIR, RelatedLocation
from scieqlint.diag.model import Diagnostic, Severity, SourceSpan
from scieqlint.engine.base import Engine
from scieqlint.facts.generated import GeneratedProvenanceFact
from scieqlint.facts.math import DisplayMathFact, InlineMathFact, UnknownMathFact
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.facts.project import HiddenExcludedFact, ProjectMemberFact
from scieqlint.facts.reference import EquationLabelFact, GenericRefFact, TargetAnchorFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.facts.structure import (
    CodeCellFact,
    DirectiveFact,
    FenceFact,
    HeadingFact,
    SectionFact,
    StructureSyntaxIssueFact,
)
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.ir.model import DocumentIR, FrontendResult
from scieqlint.query.host import QueryHost
from scieqlint.schema.result import AnalysisResult
from scieqlint.source.maps import SourceMap


def doc(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def mutate_inline_body(inline: Any) -> None:
    inline.body = "y"


def engine_rule_codes(engine: Engine) -> frozenset[str]:
    return engine.rule_codes


def span(path: str = "a.md", *, start: int = 0, end: int = 1) -> SourceSpan:
    return SourceSpan(
        path=PurePosixPath(path),
        start=start,
        end=end,
        line=1,
        col=start + 1,
        end_line=1,
        end_col=end,
    )


def test_fact_snapshot_is_deterministic_and_immutable():
    document = doc("a.md", "# Title\n\nText $x$.\n")
    inline = InlineMathFact(
        fact_id="a.md::inline-math::16",
        document_id="a.md",
        span=None,
        raw="$x$",
        body="x",
        delimiter_kind="dollar",
        context="paragraph",
    )

    snapshot = FactSnapshot(documents=(document,), inline_math=(inline,))

    assert snapshot == FactSnapshot(documents=(document,), inline_math=(inline,))
    assert snapshot.documents[0].path.as_posix() == "a.md"
    assert snapshot.all_facts() == (inline,)
    with pytest.raises(FrozenInstanceError):
        mutate_inline_body(inline)


def test_source_map_spans_use_document_offsets():
    document = doc("chapter.md", "alpha\nbeta\n")
    source_map = SourceMap.for_document(document)

    span = source_map.span(6, 10)

    assert source_map.identity.document_id == "chapter.md"
    assert source_map.identity.kind == DocumentKind.MARKDOWN.value
    assert span.path.as_posix() == "chapter.md"
    assert (span.start, span.end) == (6, 10)
    assert (span.line, span.col, span.end_line, span.end_col) == (2, 1, 2, 4)
    with pytest.raises(ValueError, match="invalid span offsets"):
        source_map.span(5, 4)


def test_snapshot_with_unknown_math_appends_without_mutating_original():
    document = doc("a.md", "Text $x$.\n")
    inline = InlineMathFact(
        fact_id="a.md::inline-math::6",
        document_id="a.md",
        span=None,
        raw="$x$",
        body="x",
        delimiter_kind="dollar",
        context="paragraph",
    )
    unknown = UnknownMathFact(
        fact_id="a.md::unknown-math::6",
        document_id="a.md",
        span=None,
        raw="$x$",
        source_math_fact_id=inline.fact_id,
        reason="macro",
        excerpt=r"\newcommand",
    )

    snapshot = FactSnapshot(documents=(document,), inline_math=(inline,))
    updated = snapshot.with_unknown_math((unknown,))

    assert snapshot.unknown_math == ()
    assert updated.inline_math == (inline,)
    assert updated.unknown_math == (unknown,)
    assert updated.all_facts() == (inline, unknown)


def test_query_host_views_expose_snapshot_contracts():
    document = doc("a.md", "Text\n")
    generated_document = doc("a.html", "<p>Text</p>\n")
    heading = HeadingFact(
        fact_id="heading-1",
        document_id="a.md",
        span=span(),
        raw="####Title",
        level=4,
        text="Title",
        slug_candidate="title",
        valid_atx=False,
        malformation="missing-space-after-marker",
    )
    section = SectionFact(
        fact_id="section-1",
        document_id="a.md",
        span=span(),
        heading_fact_id=heading.fact_id,
        parent_section_id=None,
        depth=1,
        ordinal_path=(1,),
    )
    fence = FenceFact(
        fact_id="fence-1",
        document_id="a.md",
        span=span(),
        opener="```",
        fence_char="`",
        fence_length=3,
        info_string="{python}",
        language="python",
        kind="code-cell",
        is_closed=False,
        opener_span=span(start=0, end=3),
        closer_span=None,
        body_span=span(start=4, end=8),
    )
    directive = DirectiveFact(
        fact_id="directive-1",
        document_id="a.md",
        span=span(),
        name="code-cell",
        argument="python",
        options=(("renderings", "html"), ("fig-cap", "Plot")),
        fence_fact_id=fence.fact_id,
    )
    cell = CodeCellFact(
        fact_id="cell-1",
        document_id="a.md",
        span=span(),
        fence_fact_id=fence.fact_id,
        directive_fact_id=directive.fact_id,
        language="python",
        engine="jupyter",
        options=directive.options,
        label="plot",
    )
    unlabeled_cell = CodeCellFact(
        fact_id="cell-unlabeled",
        document_id="a.md",
        span=span(),
        fence_fact_id=fence.fact_id,
        directive_fact_id=None,
        language="python",
        engine="jupyter",
        options=(),
        label=None,
    )
    non_crossref_cell = CodeCellFact(
        fact_id="cell-non-crossref",
        document_id="a.md",
        span=span(),
        fence_fact_id=fence.fact_id,
        directive_fact_id=None,
        language="python",
        engine="jupyter",
        options=(),
        label="plot-plain",
    )
    prefixed_cell = CodeCellFact(
        fact_id="cell-prefixed",
        document_id="a.md",
        span=span(),
        fence_fact_id=fence.fact_id,
        directive_fact_id=None,
        language="python",
        engine="jupyter",
        options=(),
        label="fig-plot",
    )
    source_anchor = TargetAnchorFact(
        fact_id="target-source",
        document_id="a.md",
        span=span(),
        label="Intro",
        normalized_label="intro",
        target_kind="heading",
        attaches_to_fact_id=heading.fact_id,
        placement="before_heading",
    )
    duplicate_anchor = TargetAnchorFact(
        fact_id="target-duplicate",
        document_id="a.md",
        span=span(),
        label="intro",
        normalized_label="intro",
        target_kind="heading",
        attaches_to_fact_id=heading.fact_id,
        placement="standalone",
    )
    orphaned_anchor = TargetAnchorFact(
        fact_id="target-orphaned",
        document_id="a.md",
        span=span(),
        label="Lonely",
        normalized_label="lonely",
        target_kind=None,
        attaches_to_fact_id=None,
        placement="orphaned",
    )
    ref = GenericRefFact(
        fact_id="ref-1",
        document_id="a.md",
        span=span(),
        role_kind="ref",
        target="Intro",
        normalized_target="intro",
    )
    unresolved_ref = GenericRefFact(
        fact_id="ref-missing",
        document_id="a.md",
        span=span(),
        role_kind="ref",
        target="Missing",
        normalized_target="missing",
    )
    equation = EquationLabelFact(
        fact_id="eq-label-1",
        document_id="a.md",
        span=span(),
        label="eq:energy",
        normalized_label="eq:energy",
        label_syntax_kind="myst",
        source_block_id="math-1",
    )
    inline = InlineMathFact(
        fact_id="inline-1",
        document_id="a.md",
        span=span(),
        raw="$x$",
        body="x",
        delimiter_kind="dollar",
        context="paragraph",
    )
    display = DisplayMathFact(
        fact_id="display-1",
        document_id="a.md",
        span=span(),
        raw="$$x$$",
        body="x",
        container="dollar-dollar",
        label_fact_ids=("eq-1", "eq-2"),
    )
    unknown = UnknownMathFact(
        fact_id="unknown-1",
        document_id="a.md",
        span=span(),
        raw=r"\newcommand{\x}{x}",
        source_math_fact_id=display.fact_id,
        reason="macro",
        excerpt=r"\newcommand",
    )
    member = ProjectMemberFact(
        fact_id="member-1",
        document_id="a.md",
        span=None,
        path=PurePosixPath("a.md"),
        project_root=PurePosixPath("."),
        declared=True,
        discovered=True,
        normalized_path=PurePosixPath("chapter.md"),
    )
    duplicate_member = ProjectMemberFact(
        fact_id="member-2",
        document_id="b.md",
        span=None,
        path=PurePosixPath("./a.md"),
        project_root=PurePosixPath("."),
        declared=False,
        discovered=True,
        normalized_path=PurePosixPath("chapter.md"),
    )
    hidden = HiddenExcludedFact(
        fact_id="hidden-1",
        document_id=".secret.md",
        span=None,
        path=PurePosixPath(".secret.md"),
        reason="hidden",
    )
    excluded = HiddenExcludedFact(
        fact_id="excluded-1",
        document_id="build/out.md",
        span=None,
        path=PurePosixPath("build/out.md"),
        reason="excluded",
    )
    provenance = GeneratedProvenanceFact(
        fact_id="generated-1",
        document_id="a.html",
        span=None,
        generated_document_id="a.html",
        source_document_id="a.md",
        source_sha="abc123",
    )
    portability = OutputPortabilityFact(
        fact_id="portability-1",
        document_id="a.md",
        span=span(),
        subject_fact_id=cell.fact_id,
        output_profile="quarto-html",
        risk_kind="crossref-label",
    )
    syntax_issue = StructureSyntaxIssueFact(
        fact_id="syntax-1",
        document_id="a.md",
        span=span(),
        raw="{ref}target",
        kind="myst-role",
        reason="malformed MyST role syntax",
    )

    snapshot = FactSnapshot(
        documents=(document, generated_document),
        headings=(heading,),
        sections=(section,),
        fences=(fence,),
        directives=(directive,),
        code_cells=(cell, unlabeled_cell, non_crossref_cell, prefixed_cell),
        structure_syntax_issues=(syntax_issue,),
        target_anchors=(source_anchor, duplicate_anchor, orphaned_anchor),
        generic_refs=(ref, unresolved_ref),
        equation_labels=(equation,),
        inline_math=(inline,),
        display_math=(display,),
        unknown_math=(unknown,),
        project_members=(member, duplicate_member),
        hidden_excluded=(hidden, excluded),
        generated_provenance=(provenance,),
        portability=(portability,),
    )
    query = QueryHost(snapshot)

    assert query.structure.headings() == (heading,)
    assert query.structure.sections() == (section,)
    assert query.structure.fences() == (fence,)
    assert query.structure.directives() == (directive,)
    assert query.structure.code_cells() == (cell, unlabeled_cell, non_crossref_cell, prefixed_cell)
    assert query.structure.syntax_issues() == (syntax_issue,)
    assert query.structure.malformed_headings() == (heading,)
    assert query.structure.unclosed_fences() == (fence,)
    assert directive.option_dict() == {"renderings": "html", "fig-cap": "Plot"}
    assert cell.option_dict() == directive.option_dict()

    assert query.references.generic_targets() == (
        source_anchor,
        duplicate_anchor,
        orphaned_anchor,
    )
    assert query.references.equation_targets() == (equation,)
    assert query.references.generic_refs() == (ref, unresolved_ref)
    assert query.references.target_index()["intro"] == (source_anchor, duplicate_anchor)
    assert query.references.duplicate_generic_targets() == {
        "intro": (source_anchor, duplicate_anchor)
    }
    assert query.references.unresolved_generic_refs() == (unresolved_ref,)
    assert query.references.ambiguous_generic_refs() == (ref,)
    assert query.references.orphaned_targets() == (orphaned_anchor,)

    assert query.math.inline_math() == (inline,)
    assert query.math.display_math() == (display,)
    assert query.math.unknown_math() == (unknown,)
    assert query.math.display_with_multiple_labels() == (display,)

    assert query.generated.provenance() == (provenance,)
    assert query.generated.generated_document_ids() == ("a.html",)
    assert query.generated.dropped_targets() == (
        (provenance, duplicate_anchor),
        (provenance, orphaned_anchor),
    )

    assert query.project.members() == (member, duplicate_member)
    assert query.project.hidden_files() == (hidden,)
    assert query.project.excluded_files() == (excluded,)
    assert query.project.duplicate_normalized_paths() == {
        PurePosixPath("chapter.md"): (member, duplicate_member)
    }

    assert query.portability.inline_math_missing_alt() == (inline,)
    assert query.portability.display_math_missing_alt() == (display,)
    assert query.portability.quarto_crossref_label_issues() == (cell,)
    assert query.portability.renderings_with_crossref_options() == (cell,)
    assert snapshot.all_facts()[-1] == portability


def test_diagnostic_ir_result_and_frontend_contracts_are_projected():
    class NoopEngine:
        name = "noop"
        rule_codes = frozenset({"STR001"})

        def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
            return ()

    document = doc("a.md", "Text\n")
    location = RelatedLocation(span=span(start=1, end=2), message="related")
    diagnostic_ir = DiagnosticIR(
        code="STR001",
        message="Heading marker must be followed by a space",
        span=span(),
        severity_default=Severity.WARNING,
        detail="The heading is parsed differently by downstream renderers.",
        hint="Add a space after the heading marker.",
        rule="heading-atx-space",
        related_locations=(location,),
    )

    diagnostic = diagnostic_ir.to_diagnostic(Severity.ERROR)
    snapshot = FactSnapshot(documents=(document,))
    result = AnalysisResult(
        snapshot=snapshot,
        diagnostics=(
            diagnostic,
            Diagnostic("REF001", Severity.WARNING, "missing target", None),
            Diagnostic("INF001", Severity.INFO, "note", None),
        ),
        profiles=("scientific-myst",),
    )
    document_ir = DocumentIR(document_id="a.md", document=document, facts=())
    frontend_result = FrontendResult(documents=(document_ir,))

    assert diagnostic.severity is Severity.ERROR
    assert diagnostic.detail == diagnostic_ir.detail
    assert diagnostic.hint == diagnostic_ir.hint
    assert diagnostic.rule == diagnostic_ir.rule
    assert diagnostic_ir.related_locations == (location,)
    assert result.schema_version == "0.2-architecture-preview"
    assert result.summary() == {
        "files_checked": 1,
        "facts": 0,
        "diagnostics": 3,
        "errors": 1,
        "warnings": 1,
        "info": 1,
    }
    assert frontend_result.documents == (document_ir,)
    assert engine_rule_codes(NoopEngine()) == frozenset({"STR001"})
