"""Profile fact-snapshot composition at the application boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path, PurePosixPath

from scieqlint.config.model import Config, ProjectVisibility
from scieqlint.facts.generated import GeneratedProvenanceFact
from scieqlint.facts.math import DisplayMathFact, InlineMathFact
from scieqlint.facts.reference import CrossrefMetadataFact, EquationLabelFact, EquationRefFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.crossref import crossref_metadata_facts
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.frontend.notebook import NotebookFrontend
from scieqlint.frontend.notebook_input import NotebookInput, NotebookSourceLocationError
from scieqlint.frontend.reference_display import reference_display_text_facts
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.io.workspace import WorkspaceHost
from scieqlint.parse.math import MathHost
from scieqlint.policy import PolicyHost
from scieqlint.scan.base import EquationLabel, EquationReference, MathContainer
from scieqlint.scan.latex import LatexScanner

from .app_profile_crossref import source_label_facts, source_reference_facts
from .app_profile_generated import generated_provenance_facts


def profile_snapshot(
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
    workspace: WorkspaceHost | None = None,
) -> FactSnapshot:
    snapshot = generated_profile_snapshot(
        documents,
        config,
        source_references=source_references,
        source_labels=source_labels,
        generated_provenance=generated_provenance,
        frontend_snapshot=frontend_snapshot,
        accessibility_metadata=accessibility_metadata,
        parsed_notebooks=parsed_notebooks,
        notebook_location_errors=notebook_location_errors,
        workspace=workspace,
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


def generated_profile_snapshot(
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
    workspace: WorkspaceHost | None = None,
) -> FactSnapshot:
    """Build one profile snapshot from caller-owned source-to-generated mappings."""

    if workspace is None:
        project_root = config.project.root
        if any(document.path.is_absolute() for document in documents):
            root = Path(project_root.as_posix())
            if not root.is_absolute() and config.path is not None:
                root = Path(config.path.as_posix()).parent / root
            project_root = PurePosixPath(root.absolute().as_posix())
        workspace = WorkspaceHost(project_root=project_root)
    markdown_documents = tuple(
        document for document in documents if document.kind is DocumentKind.MARKDOWN
    )
    notebook_documents = tuple(
        document for document in documents if document.kind is DocumentKind.NOTEBOOK
    )
    snapshot = (
        MySTFrontend(workspace=workspace).lower(
            markdown_documents,
            _include_reference_display=False,
        )
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
                *latex_display_facts(latex_math_documents, config),
            ),
        )
    labels = source_label_facts(documents, source_labels, config)
    references = source_reference_facts(documents, source_references, config)
    notebook_full_profile = config.profile.name in {
        "cross-format-references",
        "math-accessibility",
        "notebook-crossrefs",
        "reference-display",
        "code-cell-metadata",
    }
    if notebook_documents and (config.checks.references.enabled or notebook_full_profile):
        notebook_snapshot = NotebookFrontend(workspace=workspace).lower(
            notebook_documents,
            parsed=parsed_notebooks,
            _source_location_errors=notebook_location_errors,
            _include_markdown=(
                config.scanner.markdown or config.profile.name == "reference-display"
            ),
            _include_reference_display=False,
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
        equation_labels=(*snapshot.equation_labels, *labels),
        equation_refs=(*snapshot.equation_refs, *references),
    )
    snapshot = replace(
        snapshot,
        inline_math=apply_accessibility_metadata(
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
        reference_display_text=(
            reference_display_text_facts(
                snapshot.generic_refs,
                snapshot.equation_refs,
                snapshot.target_anchors,
                snapshot.equation_labels,
                project_root=workspace.project_root,
                code_cells=snapshot.code_cells,
            )
            if config.profile.name == "reference-display"
            else ()
        ),
    )
    provenance = (
        generated_provenance_facts(markdown_documents, config)
        if generated_provenance is None
        else tuple(generated_provenance)
    )
    if provenance:
        return replace(snapshot, generated_provenance=provenance)
    return snapshot


def latex_display_facts(
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


def apply_accessibility_metadata(
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
