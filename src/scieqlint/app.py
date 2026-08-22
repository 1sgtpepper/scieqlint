"""Application orchestration layer."""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePath, PurePosixPath
from typing import Generic, TypeVar, cast

from scieqlint import __version__
from scieqlint.check.algebra import check_algebra
from scieqlint.check.dimensions import check_dimensions
from scieqlint.check.references import check_missing_labels, check_references
from scieqlint.check.suppressions import apply_suppressions
from scieqlint.check.symbols import check_symbols
from scieqlint.config.load import _load_config_with_inputs  # pyright: ignore[reportPrivateUsage]
from scieqlint.config.model import AlgebraConfig, Config, ParserConfig, ProjectVisibility
from scieqlint.diag.baseline import (
    BaselineIdentity,
    apply_baseline,
    baseline_identities_from_json,
)
from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import CheckResult, Diagnostic, Severity, SourceSpan
from scieqlint.engine.generated import GeneratedOutputEngine
from scieqlint.engine.portability import PortabilityEngine
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.engine.structure import StructureEngine
from scieqlint.facts.generated import (
    GENERATED_PROVENANCE_FACT_SUFFIX,
    GeneratedProvenanceFact,
)
from scieqlint.facts.math import DisplayMathFact, InlineMathFact
from scieqlint.facts.reference import (
    CrossrefMetadataFact,
    EquationLabelFact,
    EquationRefFact,
)
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.crossref import crossref_metadata_facts
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.frontend.notebook import NotebookFrontend
from scieqlint.frontend.notebook_input import (
    NotebookInput,
    NotebookSourceLocationError,
)
from scieqlint.frontend.notebook_input import (
    input_diagnostic as _input_diagnostic,
)
from scieqlint.frontend.reference_display import reference_display_text_facts
from scieqlint.graph.export import build_graph
from scieqlint.graph.model import Graph, GraphNode
from scieqlint.io.discover import discover_files
from scieqlint.io.identity import ConsumedInput, open_text
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.io.workspace import WorkspaceHost
from scieqlint.parse.math import MathHost
from scieqlint.policy import PolicyHost
from scieqlint.query.host import QueryHost
from scieqlint.scan.base import (
    EquationLabel,
    EquationReference,
    LabelSource,
    MathBlock,
    MathContainer,
    ReferenceSource,
    SymbolDirective,
)
from scieqlint.scan.latex import LatexScanner
from scieqlint.scan.markdown import (
    MarkdownScanner,
    _mask_ranges,  # pyright: ignore[reportPrivateUsage]
)
from scieqlint.scan.notebook import NotebookScanner
from scieqlint.schema import SchemaHost

_ResultT = TypeVar("_ResultT")


@dataclass(frozen=True, slots=True)
class _AnalysisRun(Generic[_ResultT]):
    """An analysis result paired with identities captured while its inputs were read."""

    result: _ResultT
    consumed_inputs: tuple[ConsumedInput, ...]
    input_identities_complete: bool


def check_paths(
    paths: Sequence[Path | str],
    *,
    config_path: Path | str | None = None,
    no_algebra: bool = False,
    inline_math: bool = False,
    strict_unknowns: bool = False,
    absolute_paths: bool = False,
) -> CheckResult:
    """Load supported files and check them."""
    return _run_check_paths(
        paths,
        config_path=config_path,
        no_algebra=no_algebra,
        inline_math=inline_math,
        strict_unknowns=strict_unknowns,
        absolute_paths=absolute_paths,
    ).result


def _run_check_paths(
    paths: Sequence[Path | str],
    *,
    config_path: Path | str | None = None,
    no_algebra: bool = False,
    inline_math: bool = False,
    strict_unknowns: bool = False,
    absolute_paths: bool = False,
) -> _AnalysisRun[CheckResult]:
    """Load supported files, check them, and retain their consumed identities."""
    config, config_inputs = _load_config_with_inputs(config_path)
    config = _apply_overrides(
        config,
        no_algebra=no_algebra,
        inline_math=inline_math,
        strict_unknowns=strict_unknowns,
    )
    project_root, discovered = _discover_project_files(paths, config)
    analysis_config = _analysis_config(config, project_root)
    presentation_paths: dict[PurePosixPath, PurePosixPath] = {}
    documents: list[SourceDocument] = []
    diagnostics: list[Diagnostic] = []
    consumed_inputs = list(config_inputs)
    input_identities_complete = _consumed_inputs_complete(consumed_inputs)

    for path in discovered:
        consumed_count = len(consumed_inputs)
        try:
            analysis_path = _analysis_source_path(path, config=config)
            presentation_paths[analysis_path] = _display_path(
                path,
                absolute_paths=absolute_paths,
            )
            document = _load_source(
                path,
                document_path=analysis_path,
                consumed_inputs=consumed_inputs,
            )
        except (OSError, UnicodeError) as exc:
            if len(consumed_inputs) == consumed_count:
                input_identities_complete = False
            diagnostics.append(_source_read_diagnostic(path, exc, absolute_paths=absolute_paths))
            continue
        documents.append(document)

    result = check_documents(documents, config=analysis_config)
    presented = _present_diagnostic_paths(result.diagnostics, presentation_paths)
    diagnostics_result = tuple(sorted((*diagnostics, *presented), key=_diagnostic_key))
    baselines = _load_baselines(config, project_root, consumed_inputs)
    input_identities_complete = input_identities_complete and _consumed_inputs_complete(
        consumed_inputs
    )
    diagnostics_result = apply_baseline(
        diagnostics_result,
        baselines,
    )
    return _AnalysisRun(
        CheckResult(
            diagnostics=diagnostics_result,
            files_checked=len(discovered),
            math_blocks_checked=result.math_blocks_checked,
            config_path=config.path,
            version=__version__,
            show_suppressed=config.report.show_suppressed,
        ),
        tuple(consumed_inputs),
        input_identities_complete,
    )


def check_documents(
    documents: Sequence[SourceDocument],
    *,
    config: Config,
    accessibility_metadata: Mapping[str, str] | None = None,
) -> CheckResult:
    """Check already-loaded documents with caller-owned accessibility metadata."""
    normalized_accessibility_metadata = _normalize_accessibility_metadata(accessibility_metadata)
    if normalized_accessibility_metadata and config.profile.name != "math-accessibility":
        raise ValueError('accessibility_metadata requires profile.name = "math-accessibility"')
    if config.profile.name in {
        "generated-myst",
        "cross-format-references",
        "notebook-crossrefs",
        "typst-portability",
    }:
        # Profile facts and diagnostics use the lexical path as their source identity.
        seen_paths: set[PurePosixPath] = set()
        duplicate_paths: set[PurePosixPath] = set()
        for document in documents:
            if document.path in seen_paths:
                duplicate_paths.add(document.path)
            else:
                seen_paths.add(document.path)
        if duplicate_paths:
            paths = ", ".join(
                path.as_posix()
                for path in sorted(duplicate_paths, key=lambda path: path.as_posix())
            )
            raise ValueError(f"duplicate document path(s): {paths}")

    workspace = WorkspaceHost(project_root=_workspace_root(config, documents))
    members, _hidden_excluded = workspace.project_facts(
        documents,
        config.project.visibility,
    )
    project_members = members
    visible_document_ids = {
        member.document_id for member in members if member.visibility == "visible"
    }
    markdown_documents = tuple(
        document for document in documents if document.kind is DocumentKind.MARKDOWN
    )
    frontend_snapshot = FactSnapshot()
    raw_opaque_spans: tuple[SourceSpan, ...] = ()
    if config.scanner.markdown:
        # Capture candidates before MathHost drops non-math and incomplete forms;
        # the legacy scanner must not reinterpret any raw candidate's contents.
        frontend_snapshot = MySTFrontend(workspace=workspace).lower(markdown_documents)
        raw_opaque_spans = tuple(
            fact.span
            for fact in frontend_snapshot.display_math
            if fact.source_syntax == "raw-latex" and fact.span is not None
        )

    scanner = MarkdownScanner(workspace=workspace)
    latex_scanner = LatexScanner()
    notebook_scanner = NotebookScanner(workspace=workspace)
    parsed_notebooks: dict[str, NotebookInput] = {}
    path_order = {document.path.as_posix(): index for index, document in enumerate(documents)}
    blocks: list[MathBlock] = []
    labels: list[EquationLabel] = []
    non_markdown_labels: list[EquationLabel] = []
    non_markdown_references: list[EquationReference] = []
    references: list[EquationReference] = []
    symbol_directives: list[SymbolDirective] = []
    diagnostics: list[Diagnostic] = []
    profile_documents = tuple(
        document
        for document in documents
        if (
            document.kind is DocumentKind.MARKDOWN
            and (config.scanner.markdown or config.profile.name == "reference-display")
        )
        or (
            document.kind is DocumentKind.LATEX
            and config.profile.name in {"cross-format-references", "typst-portability"}
        )
        or (
            document.kind is DocumentKind.NOTEBOOK
            and (
                config.checks.references.enabled
                or config.profile.name
                in {
                    "cross-format-references",
                    "math-accessibility",
                    "notebook-crossrefs",
                    "reference-display",
                }
            )
        )
    )
    if not profile_documents and normalized_accessibility_metadata is not None:
        _apply_accessibility_metadata((), normalized_accessibility_metadata)

    for document in documents:
        if document.kind is DocumentKind.LATEX:
            scan = latex_scanner.scan(document, config)
        elif document.kind is DocumentKind.MARKDOWN:
            scan = scanner.scan(_legacy_markdown_document(document, raw_opaque_spans), config)
        elif document.kind is DocumentKind.NOTEBOOK:
            parsed = notebook_scanner.parse(document)
            parsed_notebooks[document.path.as_posix()] = parsed
            scan = notebook_scanner.scan(document, config, parsed=parsed)
        else:
            raise _unsupported_source_kind(document.path)
        blocks.extend(scan.blocks)
        labels.extend(scan.labels)
        if document.kind is not DocumentKind.MARKDOWN:
            non_markdown_labels.extend(scan.labels)
            non_markdown_references.extend(scan.references)
        references.extend(scan.references)
        symbol_directives.extend(scan.symbol_directives)
        diagnostics.extend(scan.diagnostics)
        for block in scan.blocks:
            block_diagnostics = check_algebra(block)
            if config.checks.algebra.enabled:
                diagnostics.extend(block_diagnostics)
            else:
                diagnostics.extend(
                    diagnostic
                    for diagnostic in block_diagnostics
                    if diagnostic.code.startswith("PARSE")
                )
            diagnostics.extend(check_dimensions(block, config))

    canonical_reference_path = bool(
        (
            markdown_documents
            and (config.scanner.markdown or config.profile.name == "reference-display")
        )
        or non_markdown_labels
        or non_markdown_references
    )
    if config.parser.strict_unknowns:
        diagnostics = [_strict_unknown(diagnostic) for diagnostic in diagnostics]
    if config.checks.references.enabled:
        if canonical_reference_path:
            if config.checks.references.missing_label_strict:
                diagnostics.extend(
                    check_missing_labels(
                        tuple(
                            block
                            for block in blocks
                            if _span_document_id(block.span) in visible_document_ids
                        ),
                        tuple(
                            label
                            for label in labels
                            if _span_document_id(label.span) in visible_document_ids
                        ),
                    )
                )
        else:
            diagnostics.extend(
                check_references(
                    tuple(
                        label
                        for label in labels
                        if _span_document_id(label.span) in visible_document_ids
                    ),
                    tuple(
                        reference
                        for reference in references
                        if _span_document_id(reference.span) in visible_document_ids
                    ),
                    blocks=tuple(
                        block
                        for block in blocks
                        if _span_document_id(block.span) in visible_document_ids
                    ),
                    strict_missing_labels=config.checks.references.missing_label_strict,
                    project_root=config.project.root,
                )
            )
    if config.checks.symbols.enabled:
        diagnostics.extend(
            check_symbols(
                tuple(blocks),
                tuple(symbol_directives),
                path_order=path_order,
            )
        )
    generated_provenance = _generated_provenance_facts(markdown_documents, config)
    generated_provenance_by_id = {
        provenance.fact_id: provenance for provenance in generated_provenance
    }
    generated_provenance_by_document = {
        provenance.generated_document_id: provenance for provenance in generated_provenance
    }
    if not config.scanner.inline_math and config.profile.name != "math-accessibility":
        # Inline math is opt-in, and candidate facts are lowered before scanner
        # options are applied. Standalone equation-like candidates are generated
        # output artifacts rather than inline math; retain their plain-text source
        # facts so MathHost can classify them while excluding explicit inline
        # surfaces from the profile snapshot.
        equation_text_source_ids = {
            fact.source_math_fact_id
            for fact in frontend_snapshot.generated_formulas
            if fact.candidate_kind == "equation-like-text" and fact.source_math_fact_id is not None
        }
        disabled_inline_math_ids = {
            fact.fact_id for fact in frontend_snapshot.inline_math
        } - equation_text_source_ids
        frontend_snapshot = replace(
            frontend_snapshot,
            inline_math=tuple(
                fact
                for fact in frontend_snapshot.inline_math
                if fact.fact_id not in disabled_inline_math_ids
            ),
            generated_formulas=tuple(
                fact
                for fact in frontend_snapshot.generated_formulas
                if fact.source_math_fact_id not in disabled_inline_math_ids
            ),
        )
    if canonical_reference_path or profile_documents:
        policy = PolicyHost(output_profile=config.profile.output_profile)
        notebook_location_errors: list[tuple[SourceDocument, NotebookSourceLocationError]] = []
        snapshot = _profile_snapshot(
            profile_documents,
            config,
            source_references=tuple(non_markdown_references),
            source_labels=tuple(non_markdown_labels),
            policy=policy,
            generated_provenance=generated_provenance,
            frontend_snapshot=frontend_snapshot,
            accessibility_metadata=normalized_accessibility_metadata,
            parsed_notebooks=parsed_notebooks,
            notebook_location_errors=notebook_location_errors,
        )
        # Profile facts may intentionally omit source kinds that the selected
        # profile does not inspect. Keep membership complete so path-bearing
        # references can still resolve to an included LaTeX or notebook target.
        snapshot = replace(snapshot, project_members=project_members)
        for document, exc in notebook_location_errors:
            diagnostic = _input_diagnostic(document, exc)
            if diagnostic not in diagnostics:
                diagnostics.append(diagnostic)
        query = QueryHost(snapshot)
        diagnostics = _without_profile_owned_legacy_reference_diagnostics(
            diagnostics,
            query,
        )
        if config.checks.references.enabled:
            diagnostics.extend(
                diagnostic.to_diagnostic()
                for diagnostic in ReferenceEngine(profile=config.profile.name).run(query)
            )
            if config.checks.references.missing_label_strict:
                diagnostics.extend(_raw_missing_label_diagnostics(query, visible_document_ids))
        diagnostics.extend(
            diagnostic.to_diagnostic() for diagnostic in StructureEngine().run(query)
        )
        # This compatibility path is the current shared owner for loaded and
        # path-based checks. Keep profile dispatch here until the planned
        # project-mode/AnalysisSession owner for issue #90 is available.
        if config.profile.name == "generated-myst":
            diagnostics.extend(
                diagnostic.to_diagnostic()
                for diagnostic in GeneratedOutputEngine(profile=config.profile.name).run(query)
            )
        elif config.profile.name in {
            "cross-format-references",
            "math-accessibility",
            "notebook-crossrefs",
            "typst-portability",
        }:
            diagnostics.extend(
                diagnostic.to_diagnostic()
                for diagnostic in PortabilityEngine(
                    profile=config.profile.name,
                    policy=policy,
                ).run(query)
            )
    diagnostics = list(
        apply_suppressions(
            diagnostics,
            documents=documents,
            blocks=blocks,
            raw_display_spans=raw_opaque_spans,
        )
    )
    if config.profile.name == "generated-myst":
        diagnostics = [
            _project_generated_diagnostic(
                diagnostic,
                profile=config.profile.name,
                generated_provenance_by_id=generated_provenance_by_id,
                generated_provenance_by_document=generated_provenance_by_document,
            )
            for diagnostic in diagnostics
        ]
    return CheckResult(
        diagnostics=tuple(sorted(diagnostics, key=_diagnostic_key)),
        files_checked=len(documents),
        math_blocks_checked=len(blocks),
        config_path=config.path,
        version=__version__,
        show_suppressed=config.report.show_suppressed,
    )


def _legacy_markdown_document(
    document: SourceDocument, raw_spans: Sequence[SourceSpan]
) -> SourceDocument:
    """Preserve source coordinates while hiding raw owners before delimiter pairing."""
    ranges = tuple(
        (span.start, span.end)
        for span in raw_spans
        if span.path == document.path and span.cell is None
    )
    if not ranges:
        return document
    return replace(document, text=_mask_ranges(document.text, ranges))


def _span_is_within_any(span: SourceSpan, containers: Sequence[SourceSpan]) -> bool:
    """Return whether a fact span belongs to one of the source-owned ranges."""

    return any(
        container.path == span.path
        and container.cell == span.cell
        and container.start <= span.start
        and span.end <= container.end
        for container in containers
    )


def _without_profile_owned_legacy_reference_diagnostics(
    diagnostics: list[Diagnostic],
    query: QueryHost,
) -> list[Diagnostic]:
    profile_owned_spans = {
        span
        for fact in query.references.equation_refs()
        if (span := fact.target_span or fact.span) is not None
    }
    unresolved_generic_ids = {fact.fact_id for fact in query.references.unresolved_generic_refs()}
    profile_owned_spans.update(
        span
        for fact in query.references.generic_refs()
        if not (
            fact.fact_id in unresolved_generic_ids
            and fact.role_kind == "markdown-link"
            and fact.raw_target_path is None
        )
        if (span := fact.target_span or fact.span) is not None
    )
    owned_spans = tuple(profile_owned_spans)
    return [
        diagnostic
        for diagnostic in diagnostics
        if not (
            diagnostic.code == "REF002"
            and diagnostic.span is not None
            and _span_is_within_any(diagnostic.span, owned_spans)
        )
    ]


def _raw_missing_label_diagnostics(
    query: QueryHost,
    visible_document_ids: set[str],
) -> tuple[Diagnostic, ...]:
    info = CATALOG["REF003"]
    diagnostics: list[Diagnostic] = []
    for fact in query.math.display_math():
        if (
            fact.document_id not in visible_document_ids
            or fact.source_syntax != "raw-latex"
            or fact.container != "ams"
            or not fact.complete
            or fact.label_fact_ids
        ):
            continue
        assert fact.span is not None, "raw-LaTeX display facts retain source spans"
        diagnostics.append(
            Diagnostic(
                code=info.code,
                severity=info.severity,
                message=info.message,
                span=fact.span,
                equation=fact.body,
                rule="references",
            )
        )
    return tuple(diagnostics)


def _generated_provenance_facts(
    documents: Sequence[SourceDocument],
    config: Config,
) -> tuple[GeneratedProvenanceFact, ...]:
    """Build caller-owned source-to-generated mappings independently of scanning."""

    if config.profile.name != "generated-myst":
        return ()
    return tuple(
        GeneratedProvenanceFact(
            fact_id=f"{document.path.as_posix()}{GENERATED_PROVENANCE_FACT_SUFFIX}",
            document_id=document.path.as_posix(),
            span=None,
            raw=None,
            confidence="generated",
            generated_document_id=document.path.as_posix(),
            source_document_id=document.origin.source_document_id,
            source_kind=(
                document.origin.source_kind
                if document.origin.source_kind is not None
                else config.profile.source_kind
            ),
            conversion_stage=(
                document.origin.conversion_stage
                if document.origin.conversion_stage is not None
                else config.profile.conversion_stage
            ),
            source_sha=document.origin.source_sha,
            tool=document.origin.tool,
            tool_version=document.origin.tool_version,
            preserved_anchor_inventory=document.origin.preserved_anchor_inventory,
        )
        for document in documents
        if document.origin is not None
    )


def _legacy_span_identity(span: SourceSpan) -> str:
    cell = "" if span.cell is None else f"::cell-{span.cell}"
    return f"{span.start}:{span.end}{cell}"


def _legacy_equation_label_fact(label: EquationLabel) -> EquationLabelFact:
    path = label.span.path.as_posix()
    return EquationLabelFact(
        fact_id=(
            f"{path}::legacy-equation-label::{label.source.value}::"
            f"{_legacy_span_identity(label.span)}"
        ),
        document_id=path,
        span=label.span,
        raw=label.label,
        confidence="source",
        label=label.label,
        normalized_label=label.label,
        label_syntax_kind=f"legacy-{label.source.value}",
        source_block_id=label.block_id,
        label_span=label.span,
    )


def _profile_snapshot(
    documents: Sequence[SourceDocument],
    config: Config,
    *,
    source_references: Sequence[EquationReference] | None = None,
    source_labels: Sequence[EquationLabel] | None = None,
    policy: PolicyHost | None = None,
    generated_provenance: Sequence[GeneratedProvenanceFact] | None = None,
    frontend_snapshot: FactSnapshot | None = None,
    accessibility_metadata: Mapping[str, str] | None = None,
    parsed_notebooks: Mapping[str, NotebookInput] | None = None,
    notebook_location_errors: (
        list[tuple[SourceDocument, NotebookSourceLocationError]] | None
    ) = None,
) -> FactSnapshot:
    snapshot = _generated_profile_snapshot(
        documents,
        config,
        source_references=source_references,
        source_labels=source_labels,
        generated_provenance=generated_provenance,
        frontend_snapshot=frontend_snapshot,
        accessibility_metadata=accessibility_metadata,
        parsed_notebooks=parsed_notebooks,
        notebook_location_errors=notebook_location_errors,
    )
    if config.profile.name == "cross-format-references":
        return replace(
            snapshot,
            portability=(
                policy or PolicyHost(config.profile.output_profile)
            ).cross_format_reference_risks(snapshot),
        )
    if config.profile.name == "typst-portability":
        return replace(snapshot, portability=MathHost().typst_portability(snapshot))
    return snapshot


def _generated_profile_snapshot(
    documents: Sequence[SourceDocument],
    config: Config,
    *,
    source_references: Sequence[EquationReference] | None = None,
    source_labels: Sequence[EquationLabel] | None = None,
    generated_provenance: Sequence[GeneratedProvenanceFact] | None = None,
    frontend_snapshot: FactSnapshot | None = None,
    accessibility_metadata: Mapping[str, str] | None = None,
    parsed_notebooks: Mapping[str, NotebookInput] | None = None,
    notebook_location_errors: (
        list[tuple[SourceDocument, NotebookSourceLocationError]] | None
    ) = None,
) -> FactSnapshot:
    """Build one profile snapshot from caller-owned source-to-generated mappings."""

    workspace = WorkspaceHost(project_root=_workspace_root(config, documents))
    markdown_documents = tuple(
        document for document in documents if document.kind is DocumentKind.MARKDOWN
    )
    notebook_documents = tuple(
        document for document in documents if document.kind is DocumentKind.NOTEBOOK
    )
    snapshot = (
        MySTFrontend(workspace=workspace).lower(markdown_documents)
        if frontend_snapshot is None
        else frontend_snapshot
    )
    latex_math_documents = tuple(
        document
        for document in documents
        if document.kind is DocumentKind.LATEX and config.profile.name == "typst-portability"
    )
    if latex_math_documents:
        snapshot = replace(
            snapshot,
            display_math=(
                *snapshot.display_math,
                *_latex_display_facts(latex_math_documents, config),
            ),
        )
    source_label_facts = _source_label_facts(documents, source_labels, config)
    source_reference_facts = _source_reference_facts(documents, source_references, config)
    notebook_full_profile = config.profile.name in {
        "cross-format-references",
        "math-accessibility",
        "notebook-crossrefs",
        "reference-display",
    }
    if notebook_documents and (config.checks.references.enabled or notebook_full_profile):
        notebook_snapshot = NotebookFrontend(workspace=workspace).lower(
            notebook_documents,
            parsed=parsed_notebooks,
            _source_location_errors=notebook_location_errors,
            _include_markdown=(
                config.scanner.markdown or config.profile.name == "reference-display"
            ),
        )
        if notebook_full_profile:
            snapshot = replace(
                snapshot,
                documents=tuple(documents),
                inline_math=(*snapshot.inline_math, *notebook_snapshot.inline_math),
                display_math=(*snapshot.display_math, *notebook_snapshot.display_math),
                unknown_math=(*snapshot.unknown_math, *notebook_snapshot.unknown_math),
                generated_formulas=(
                    *snapshot.generated_formulas,
                    *notebook_snapshot.generated_formulas,
                ),
                code_cells=(*snapshot.code_cells, *notebook_snapshot.code_cells),
                notebook_outputs=notebook_snapshot.notebook_outputs,
                target_anchors=(*snapshot.target_anchors, *notebook_snapshot.target_anchors),
                generic_refs=(*snapshot.generic_refs, *notebook_snapshot.generic_refs),
                equation_labels=(*snapshot.equation_labels, *notebook_snapshot.equation_labels),
                equation_refs=(*snapshot.equation_refs, *notebook_snapshot.equation_refs),
                crossref_metadata=(
                    *snapshot.crossref_metadata,
                    *notebook_snapshot.crossref_metadata,
                ),
            )
        elif config.checks.references.enabled:
            snapshot = replace(
                snapshot,
                documents=tuple(documents),
                equation_labels=(*snapshot.equation_labels, *notebook_snapshot.equation_labels),
                equation_refs=(*snapshot.equation_refs, *notebook_snapshot.equation_refs),
            )
    snapshot = replace(
        snapshot,
        documents=tuple(documents),
        equation_labels=(*snapshot.equation_labels, *source_label_facts),
        equation_refs=(*snapshot.equation_refs, *source_reference_facts),
    )
    snapshot = replace(
        snapshot,
        inline_math=_apply_accessibility_metadata(
            snapshot.inline_math,
            accessibility_metadata,
        ),
    )
    profile_visibility: tuple[tuple[str, ProjectVisibility], ...] = workspace.project_visibility(
        documents,
        config.project.visibility,
    )
    raw_math_fact_ids = frozenset(
        fact.fact_id for fact in snapshot.display_math if fact.container == "raw-latex"
    )
    snapshot = MathHost().classify(snapshot)
    raw_labels_by_document: dict[str, list[EquationLabelFact]] = {}
    raw_refs_by_document: dict[str, list[EquationRefFact]] = {}
    for label in snapshot.equation_labels:
        if label.source_block_id in raw_math_fact_ids:
            raw_labels_by_document.setdefault(label.document_id, []).append(label)
    for reference in snapshot.equation_refs:
        if reference.source_block_id in raw_math_fact_ids:
            raw_refs_by_document.setdefault(reference.document_id, []).append(reference)
    raw_crossref_metadata: list[CrossrefMetadataFact] = []
    documents_by_id = {document.path.as_posix(): document for document in documents}
    raw_document_ids = tuple(dict.fromkeys((*raw_labels_by_document, *raw_refs_by_document)))
    for document_id in raw_document_ids:
        document = documents_by_id[document_id]
        raw_crossref_metadata.extend(
            crossref_metadata_facts(
                document,
                (),
                raw_refs_by_document.get(document_id, ()),
                workspace=workspace,
                equation_labels=raw_labels_by_document.get(document_id, ()),
            )
        )
    if raw_crossref_metadata:
        snapshot = replace(
            snapshot,
            crossref_metadata=(*snapshot.crossref_metadata, *raw_crossref_metadata),
        )
    snapshot = workspace.apply_visibility(snapshot, profile_visibility)
    snapshot = replace(
        snapshot,
        reference_display_text=reference_display_text_facts(
            snapshot.generic_refs,
            snapshot.equation_refs,
            snapshot.target_anchors,
            snapshot.equation_labels,
            project_root=workspace.project_root,
            code_cells=snapshot.code_cells,
        ),
    )
    provenance = (
        _generated_provenance_facts(markdown_documents, config)
        if generated_provenance is None
        else tuple(generated_provenance)
    )
    if provenance:
        return replace(snapshot, generated_provenance=provenance)
    return snapshot


def _legacy_equation_reference_fact(reference: EquationReference) -> EquationRefFact:
    path = reference.span.path.as_posix()
    target = reference.target
    return EquationRefFact(
        fact_id=(
            f"{path}::legacy-equation-reference::{reference.source.value}::"
            f"{_legacy_span_identity(reference.span)}"
        ),
        document_id=path,
        span=reference.span,
        raw=reference.raw,
        confidence="source",
        ref_kind=f"legacy-{reference.source.value}",
        target=target,
        normalized_target=target,
        role_span=reference.span,
        target_span=reference.span,
    )


def _latex_display_facts(
    documents: Sequence[SourceDocument],
    config: Config,
) -> tuple[DisplayMathFact, ...]:
    """Adapt complete LatexScanner blocks for source-owned Typst analysis."""

    scanner = LatexScanner()
    facts: list[DisplayMathFact] = []
    for document in documents:
        scan = scanner.scan(document, config)
        for block in scan.blocks:
            environment = {
                MathContainer.LATEX_EQUATION: "equation",
                MathContainer.LATEX_ALIGN: "align",
            }.get(block.container)
            facts.append(
                DisplayMathFact(
                    fact_id=f"{document.path.as_posix()}::latex-display::{block.span.start}",
                    document_id=document.path.as_posix(),
                    span=block.span,
                    raw=document.text[block.span.start : block.span.end],
                    body=block.text,
                    container="latex-display",
                    environment=environment,
                )
            )
    return tuple(facts)


def _project_generated_diagnostic(
    diagnostic: Diagnostic,
    *,
    profile: str,
    generated_provenance_by_id: dict[str, GeneratedProvenanceFact],
    generated_provenance_by_document: dict[str, GeneratedProvenanceFact],
) -> Diagnostic:
    """Attach only caller-owned generated origins to a public diagnostic."""
    provenances: list[GeneratedProvenanceFact] = []
    for fact_id in dict.fromkeys(diagnostic.provenance_ids):
        provenance = generated_provenance_by_id.get(fact_id)
        if provenance is not None:
            provenances.append(provenance)
    if not provenances and diagnostic.span is not None:
        provenance = generated_provenance_by_document.get(diagnostic.span.path.as_posix())
        if provenance is not None:
            provenances.append(provenance)
    if not provenances:
        return diagnostic
    projection = SchemaHost.project_diagnostic(
        diagnostic,
        profile=profile,
        provenances=tuple(provenances),
    )
    return replace(
        diagnostic,
        profile=projection.profile,
        provenance_ids=projection.provenance_ids,
        properties=projection.properties,
    )


_SOURCE_REFERENCE_KINDS = {
    ReferenceSource.MYST_EQ_ROLE: "eq",
    ReferenceSource.MYST_NUMREF_ROLE: "numref",
    ReferenceSource.LATEX_REF: "tex-ref",
    ReferenceSource.LATEX_EQREF: "tex-eqref",
}


def _source_label_facts(
    documents: Sequence[SourceDocument],
    source_labels: Sequence[EquationLabel] | None,
    config: Config,
) -> tuple[EquationLabelFact, ...]:
    labels = source_labels
    if labels is None:
        labels = tuple(
            label
            for document in documents
            if document.kind is DocumentKind.LATEX
            for label in LatexScanner().scan(document, config).labels
        )
    if config.profile.name != "cross-format-references":
        return tuple(
            _legacy_equation_label_fact(label)
            for label in labels
            if label.source is LabelSource.LATEX_LABEL
        )
    source_ids = {
        document.path.as_posix() for document in documents if document.kind is DocumentKind.LATEX
    }
    if not source_ids:
        return ()
    return tuple(
        EquationLabelFact(
            fact_id=_source_role_fact_id(label.span, "source-label"),
            document_id=label.span.path.as_posix(),
            span=label.span,
            raw=label.label,
            label=label.label,
            normalized_label=label.label.removeprefix("#").strip(),
            label_syntax_kind=label.source.value,
            source_block_id=label.block_id,
            label_span=label.span,
        )
        for label in labels
        if label.span.path.as_posix() in source_ids
    )


def _source_reference_facts(
    documents: Sequence[SourceDocument],
    source_references: Sequence[EquationReference] | None,
    config: Config,
) -> tuple[EquationRefFact, ...]:
    references = source_references
    if references is None:
        references = tuple(
            reference
            for document in documents
            if document.kind is DocumentKind.LATEX
            for reference in LatexScanner().scan(document, config).references
        )
    if config.profile.name != "cross-format-references":
        return tuple(
            _legacy_equation_reference_fact(reference)
            for reference in references
            if reference.source in {ReferenceSource.LATEX_REF, ReferenceSource.LATEX_EQREF}
        )
    source_ids = {
        document.path.as_posix() for document in documents if document.kind is DocumentKind.LATEX
    }
    if not source_ids:
        return ()
    facts: list[EquationRefFact] = []
    for reference in references:
        if reference.span.path.as_posix() not in source_ids:
            continue
        ref_kind = _SOURCE_REFERENCE_KINDS[reference.source]
        target = reference.target.strip()
        facts.append(
            EquationRefFact(
                fact_id=_source_role_fact_id(reference.span, "source-reference"),
                document_id=reference.span.path.as_posix(),
                span=reference.span,
                raw=reference.raw,
                ref_kind=ref_kind,
                target=target,
                normalized_target=target.removeprefix("#"),
                role_span=reference.span,
            )
        )
    return tuple(facts)


def _source_role_fact_id(span: SourceSpan, role: str) -> str:
    """Encode the source path, cell, role, and start as a collision-safe ID."""

    def encode(value: str) -> str:
        return f"{len(value)}:{value}"

    cell = "" if span.cell is None else str(span.cell)
    return "::".join(
        (
            f"path={encode(span.path.as_posix())}",
            f"cell={encode(cell)}",
            f"role={encode(role)}",
            f"start={encode(str(span.start))}",
        )
    )


def _apply_accessibility_metadata(
    inline_math: Sequence[InlineMathFact],
    metadata: Mapping[str, str] | None,
) -> tuple[InlineMathFact, ...]:
    if metadata is None:
        return tuple(inline_math)
    known_id_counts: dict[str, int] = {}
    for fact in inline_math:
        if fact.accessibility_id is None:
            continue
        known_id_counts[fact.accessibility_id] = known_id_counts.get(fact.accessibility_id, 0) + 1
    unknown_ids = sorted(set(metadata) - set(known_id_counts))
    if unknown_ids:
        raise ValueError(
            "accessibility metadata references unknown inline math fact(s): "
            + ", ".join(unknown_ids)
        )
    ambiguous_ids = sorted(
        accessibility_id for accessibility_id in metadata if known_id_counts[accessibility_id] > 1
    )
    if ambiguous_ids:
        raise ValueError(
            "accessibility metadata references ambiguous inline math fact(s): "
            + ", ".join(ambiguous_ids)
        )
    return tuple(
        replace(
            fact,
            alt=(metadata[fact.accessibility_id].strip() or None)
            if fact.accessibility_id is not None and fact.accessibility_id in metadata
            else fact.alt,
        )
        for fact in inline_math
    )


def _normalize_accessibility_metadata(metadata: object) -> dict[str, str] | None:
    """Validate caller metadata before it enters the fact/query pipeline."""
    if metadata is None:
        return None
    if not isinstance(metadata, Mapping):
        raise ValueError("accessibility_metadata must be a mapping")
    candidate = cast(Mapping[object, object], metadata)
    if any(not isinstance(key, str) or not key.strip() for key in candidate):
        raise ValueError("accessibility_metadata keys must be non-empty strings")
    if any(not isinstance(value, str) for value in candidate.values()):
        raise ValueError("accessibility_metadata values must be strings")
    return dict(cast(Mapping[str, str], candidate))


def graph_paths(
    paths: Sequence[Path | str],
    *,
    config_path: Path | str | None = None,
) -> Graph:
    """Load supported files and build the label/reference graph."""
    return _run_graph_paths(paths, config_path=config_path).result


def _run_graph_paths(
    paths: Sequence[Path | str],
    *,
    config_path: Path | str | None = None,
) -> _AnalysisRun[Graph]:
    """Load files, build the graph, and retain their consumed identities."""
    config, config_inputs = _load_config_with_inputs(config_path)
    project_root, discovered = _discover_project_files(paths, config)
    analysis_config = _analysis_config(config, project_root)
    presentation_paths: dict[PurePosixPath, PurePosixPath] = {}
    documents: list[SourceDocument] = []
    consumed_inputs = list(config_inputs)
    for path in discovered:
        try:
            analysis_path = _analysis_source_path(path, config=config)
            presentation_paths[analysis_path] = _display_path(path, absolute_paths=False)
            document = _load_source(
                path,
                document_path=analysis_path,
                consumed_inputs=consumed_inputs,
            )
        except (OSError, UnicodeError) as exc:
            diagnostic = _source_read_diagnostic(path, exc, absolute_paths=False)
            detail = f": {diagnostic.detail}" if diagnostic.detail else ""
            raise ValueError(f"{diagnostic.code} {diagnostic.message}{detail}") from exc
        documents.append(document)
    return _AnalysisRun(
        _present_graph_paths(
            graph_documents(documents, config=analysis_config),
            presentation_paths,
        ),
        tuple(consumed_inputs),
        _consumed_inputs_complete(consumed_inputs),
    )


def graph_documents(
    documents: Sequence[SourceDocument],
    *,
    config: Config,
) -> Graph:
    """Build graph data from already-loaded documents."""
    workspace = WorkspaceHost(project_root=_workspace_root(config, documents))
    markdown_documents = tuple(
        document for document in documents if document.kind is DocumentKind.MARKDOWN
    )
    if config.scanner.markdown:
        raw_labels, raw_references, raw_opaque_spans = _raw_graph_facts(
            markdown_documents,
            workspace=workspace,
        )
    else:
        raw_labels, raw_references, raw_opaque_spans = (), (), ()
    scanner = MarkdownScanner(workspace=workspace)
    workspace.project_facts(
        documents,
        config.project.visibility,
    )
    latex_scanner = LatexScanner()
    notebook_scanner = NotebookScanner(workspace=workspace)
    labels: list[EquationLabel] = []
    references: list[EquationReference] = []
    for document in documents:
        if document.kind is DocumentKind.LATEX:
            scan = latex_scanner.scan(document, config)
        elif document.kind is DocumentKind.MARKDOWN:
            scan = scanner.scan(_legacy_markdown_document(document, raw_opaque_spans), config)
        elif document.kind is DocumentKind.NOTEBOOK:
            scan = notebook_scanner.scan(document, config)
        else:
            raise _unsupported_source_kind(document.path)
        labels.extend(scan.labels)
        references.extend(scan.references)
    labels.extend(raw_labels)
    references.extend(raw_references)
    return build_graph(
        tuple(labels),
        tuple(references),
        project_root=workspace.project_root,
    )


def _raw_graph_facts(
    documents: Sequence[SourceDocument],
    *,
    workspace: WorkspaceHost,
) -> tuple[
    tuple[EquationLabel, ...],
    tuple[EquationReference, ...],
    tuple[SourceSpan, ...],
]:
    """Return raw graph facts and candidate spans for legacy ownership filtering."""

    frontend_snapshot = MySTFrontend(workspace=workspace).lower(documents)
    raw_opaque_spans = tuple(
        fact.span
        for fact in frontend_snapshot.display_math
        if fact.source_syntax == "raw-latex" and fact.span is not None
    )
    snapshot = MathHost().classify(frontend_snapshot)
    raw_display_ids = {
        fact.fact_id
        for fact in snapshot.display_math
        if fact.source_syntax == "raw-latex" and fact.container == "ams"
    }
    labels: list[EquationLabel] = []
    for fact in snapshot.equation_labels:
        if fact.source_block_id not in raw_display_ids:
            continue
        span = fact.label_span or fact.span
        assert span is not None, "raw-LaTeX equation labels retain source spans"
        labels.append(
            EquationLabel(
                label=fact.normalized_label,
                span=span,
                block_id=fact.source_block_id,
                source=LabelSource.LATEX_LABEL,
            )
        )
    reference_sources = {
        "tex-ref": ReferenceSource.LATEX_REF,
        "tex-eqref": ReferenceSource.LATEX_EQREF,
    }
    references: list[EquationReference] = []
    for fact in snapshot.equation_refs:
        if fact.source_block_id not in raw_display_ids:
            continue
        span = fact.target_span or fact.span
        assert span is not None, "raw-LaTeX equation references retain source spans"
        assert fact.raw is not None, "raw-LaTeX equation references retain source text"
        references.append(
            EquationReference(
                target=fact.normalized_target,
                span=span,
                raw=fact.raw,
                source=reference_sources[fact.ref_kind],
            )
        )
    return tuple(labels), tuple(references), raw_opaque_spans


def _apply_overrides(
    config: Config,
    *,
    no_algebra: bool,
    inline_math: bool,
    strict_unknowns: bool,
) -> Config:
    scanner = (
        replace(config.scanner, inline_math=True)
        if inline_math and not config.scanner.inline_math
        else config.scanner
    )
    algebra = AlgebraConfig(enabled=False) if no_algebra else config.checks.algebra
    checks = replace(config.checks, algebra=algebra)
    parser = (
        ParserConfig(strict_unknowns=True)
        if strict_unknowns and not config.parser.strict_unknowns
        else config.parser
    )
    return replace(config, scanner=scanner, checks=checks, parser=parser)


def _consumed_input_complete(consumed_input: ConsumedInput) -> bool:
    """Return whether both object and path-role metadata support safe output."""
    return consumed_input.identity is not None and consumed_input.path_metadata_complete


def _consumed_inputs_complete(consumed_inputs: Sequence[ConsumedInput]) -> bool:
    return all(_consumed_input_complete(item) for item in consumed_inputs)


def _discover_project_files(
    paths: Sequence[Path | str],
    config: Config,
) -> tuple[Path, tuple[Path, ...]]:
    project_root = _project_root(config)
    discovered = _discover_files(
        _input_paths(paths, config, project_root),
        config.ignore.files,
        config.project.order,
        reject_missing_explicit=bool(paths),
        project_root=project_root,
    )
    return project_root, discovered


def _load_source(
    path: Path,
    *,
    document_path: PurePosixPath,
    consumed_inputs: list[ConsumedInput],
) -> SourceDocument:
    kind = _document_kind(path)
    if kind is DocumentKind.UNKNOWN:
        raise _unsupported_source_kind(path)
    with open_text(path, encoding="utf-8") as (stream, consumed_input):
        consumed_inputs.append(consumed_input)
        text = stream.read()
    return SourceDocument.from_text(
        document_path,
        text,
        kind,
    )


def _source_read_diagnostic(
    path: Path,
    error: OSError | UnicodeError,
    *,
    absolute_paths: bool,
) -> Diagnostic:
    info = CATALOG["INP001"]
    detail = (
        error.strerror or type(error).__name__
        if isinstance(error, OSError)
        else getattr(error, "reason", None) or type(error).__name__
    )
    display_path = _display_path(path, absolute_paths=absolute_paths)
    return Diagnostic(
        code=info.code,
        severity=info.severity,
        message=f"{info.message}: {display_path}",
        span=_file_start_span(path, absolute_paths=absolute_paths),
        detail=detail,
    )


def _discover_files(
    paths: Sequence[Path | str],
    ignore_patterns: tuple[str, ...],
    order_patterns: tuple[str, ...] = (),
    *,
    reject_missing_explicit: bool = False,
    project_root: Path | None = None,
) -> tuple[Path, ...]:
    explicit_files: list[Path] = []
    discovered_inputs: list[Path | str] = []
    for raw in paths:
        path = Path(raw)
        if path.exists():
            if path.is_file():
                explicit_files.append(path)
            else:
                discovered_inputs.append(path)
            continue
        text = str(raw)
        has_glob = any(ch in text for ch in "*?[")
        if reject_missing_explicit and not has_glob:
            raise FileNotFoundError(f"input not found: {path}")
        discovered_inputs.append(raw)

    discovered = _filter_ignored(
        discover_files(discovered_inputs),
        ignore_patterns,
        project_root=project_root,
    )
    return tuple(
        sorted(
            {*explicit_files, *discovered},
            key=lambda path: _path_key(path, order_patterns, project_root=project_root),
        )
    )


def _filter_ignored(
    paths: Sequence[Path],
    patterns: tuple[str, ...],
    *,
    project_root: Path | None = None,
) -> tuple[Path, ...]:
    if not patterns:
        return tuple(paths)
    return tuple(
        path for path in paths if not _is_ignored(path, patterns, project_root=project_root)
    )


def _is_ignored(
    path: Path,
    patterns: tuple[str, ...],
    *,
    project_root: Path | None = None,
) -> bool:
    rel = _project_relative_path(path, project_root)
    absolute = path.resolve().as_posix()
    return any(
        fnmatch.fnmatchcase(rel, pattern) or fnmatch.fnmatchcase(absolute, pattern)
        for pattern in patterns
    )


def _input_paths(
    paths: Sequence[Path | str],
    config: Config,
    project_root: Path,
) -> tuple[Path | str, ...]:
    if paths:
        return tuple(paths)
    if config.project.order:
        return tuple(project_root / pattern for pattern in config.project.order)
    return (Path("."),)


def _workspace_root(config: Config, documents: Sequence[SourceDocument]) -> PurePosixPath:
    """Use the physical configured root when caller paths retain absolute spelling."""

    if not any(document.path.is_absolute() for document in documents):
        return config.project.root
    return PurePosixPath(_project_root(config).absolute().as_posix())


def _project_root(config: Config) -> Path:
    root = Path(config.project.root.as_posix())
    if root.is_absolute():
        return root
    if config.path is None:
        return Path.cwd() / root
    return Path(config.path.as_posix()).parent / root


def _path_key(
    path: Path,
    order_patterns: tuple[str, ...],
    *,
    project_root: Path | None,
) -> tuple[int, str]:
    rel = _project_relative_path(path, project_root)
    absolute = path.resolve().as_posix()
    for index, pattern in enumerate(order_patterns):
        if fnmatch.fnmatchcase(rel, pattern) or fnmatch.fnmatchcase(absolute, pattern):
            return (index, path.as_posix())
    return (len(order_patterns), path.as_posix())


def _project_relative_path(path: Path, project_root: Path | None) -> str:
    resolved = path.resolve()
    if project_root is not None:
        try:
            return resolved.relative_to(project_root.resolve()).as_posix()
        except ValueError:
            pass
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _load_baselines(
    config: Config,
    project_root: Path,
    consumed_inputs: list[ConsumedInput],
) -> frozenset[BaselineIdentity]:
    identities: set[BaselineIdentity] = set()
    for raw in config.baseline.files:
        path = Path(raw)
        if not path.is_absolute():
            path = project_root / path
        with open_text(path, encoding="utf-8") as (stream, consumed_input):
            consumed_inputs.append(consumed_input)
            identities.update(baseline_identities_from_json(stream.read()))
    return frozenset(identities)


def _strict_unknown(diagnostic: Diagnostic) -> Diagnostic:
    if diagnostic.code not in {"PARSE020", "PARSE021", "PARSE022"}:
        return diagnostic
    return replace(diagnostic, severity=Severity.ERROR)


def _display_path(path: Path, *, absolute_paths: bool) -> PurePosixPath:
    """Render the caller's lexical path without consulting filesystem targets."""
    if absolute_paths:
        absolute_path = path if path.is_absolute() else Path(os.path.abspath(path))
        return PurePosixPath(absolute_path.as_posix())
    if not path.is_absolute():
        return PurePosixPath(path.as_posix())
    return _lexical_relative_path(path, Path.cwd())


def _analysis_config(
    config: Config,
    project_root: Path,
) -> Config:
    """Keep the configured root in the same lexical coordinate as analysis documents."""
    analysis_base = _analysis_base(config)
    analysis_root = _lexical_relative_path(
        _absolute_lexical_path(project_root),
        analysis_base,
    )
    return replace(
        config,
        project=replace(
            config.project,
            root=analysis_root,
        ),
    )


def _analysis_source_path(path: Path, *, config: Config) -> PurePosixPath:
    """Render one source in the config-relative coordinate used by analysis."""
    return _lexical_relative_path(_absolute_lexical_path(path), _analysis_base(config))


def _analysis_base(config: Config) -> Path:
    if config.path is None:
        return Path.cwd()
    return Path(os.path.abspath(config.path.as_posix())).parent


def _absolute_lexical_path(path: Path) -> Path:
    return path if path.is_absolute() else Path(os.path.abspath(path))


def _present_diagnostic_paths(
    diagnostics: tuple[Diagnostic, ...],
    presentation_paths: Mapping[PurePosixPath, PurePosixPath],
) -> tuple[Diagnostic, ...]:
    """Restore caller-visible source paths after analysis in a stable coordinate."""
    return tuple(
        replace(
            diagnostic,
            span=(
                None
                if diagnostic.span is None
                else replace(
                    diagnostic.span,
                    path=presentation_paths.get(diagnostic.span.path, diagnostic.span.path),
                )
            ),
        )
        for diagnostic in diagnostics
    )


def _present_graph_paths(
    graph: Graph,
    presentation_paths: Mapping[PurePosixPath, PurePosixPath],
) -> Graph:
    """Restore caller-visible paths while retaining graph node identity links."""
    node_ids: dict[str, str] = {}
    presented_nodes: list[GraphNode] = []
    for node in graph.nodes:
        display_path = presentation_paths.get(node.span.path, node.span.path)
        node_id = _present_graph_id(node.id, node.span.path, display_path)
        node_ids[node.id] = node_id
        presented_nodes.append(
            replace(node, id=node_id, span=replace(node.span, path=display_path))
        )
    presented_edges = tuple(
        replace(
            edge,
            source=node_ids.get(edge.source, edge.source),
            target=node_ids.get(edge.target, edge.target),
        )
        for edge in graph.edges
    )
    return replace(graph, nodes=tuple(presented_nodes), edges=presented_edges)


def _present_graph_id(
    node_id: str,
    analysis_path: PurePosixPath,
    display_path: PurePosixPath,
) -> str:
    for prefix in ("eq:", "ref:"):
        marker = f"{prefix}{analysis_path.as_posix()}:"
        if node_id.startswith(marker):
            return f"{prefix}{display_path.as_posix()}:{node_id[len(marker) :]}"
    return node_id


def _lexical_relative_path(path: PurePath, base: PurePath) -> PurePosixPath:
    """Relativize absolute paths by components while retaining their spelling."""
    if os.path.normcase(path.anchor) != os.path.normcase(base.anchor):
        raise ValueError(
            "absolute input cannot be rendered relative to the current working directory "
            "across native roots"
        )
    path_parts = path.parts
    base_parts = base.parts
    common = 0
    for path_part, base_part in zip(path_parts, base_parts, strict=False):
        if os.path.normcase(path_part) != os.path.normcase(base_part):
            break
        common += 1
    relative_parts = ("..",) * (len(base_parts) - common) + path_parts[common:]
    return PurePosixPath(*relative_parts) if relative_parts else PurePosixPath(".")


def _document_kind(path: PurePath) -> DocumentKind:
    match path.suffix.lower():
        case ".md" | ".markdown":
            return DocumentKind.MARKDOWN
        case ".tex":
            return DocumentKind.LATEX
        case ".ipynb":
            return DocumentKind.NOTEBOOK
        case _:
            return DocumentKind.UNKNOWN


def _unsupported_source_kind(path: PurePath) -> ValueError:
    suffix = path.suffix or "<none>"
    return ValueError(f"unsupported source kind {suffix!r}: {path.as_posix()}")


def _file_start_span(path: Path, *, absolute_paths: bool) -> SourceSpan:
    display_path = _display_path(path, absolute_paths=absolute_paths)
    return SourceSpan(
        path=display_path,
        start=0,
        end=0,
        line=1,
        col=1,
        end_line=1,
        end_col=1,
    )


def _diagnostic_key(diagnostic: Diagnostic) -> tuple[str, int, int, int, str, str]:
    span = diagnostic.span
    if span is None:
        return ("", -1, 0, 0, diagnostic.code, diagnostic.message)
    cell = -1 if span.cell is None else span.cell
    return (
        span.path.as_posix(),
        cell,
        span.line,
        span.col,
        diagnostic.code,
        diagnostic.message,
    )


def _span_document_id(span: SourceSpan) -> str:
    return span.path.as_posix()
