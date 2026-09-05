"""Legacy source-reference translation at the app profile boundary."""

from __future__ import annotations

from collections.abc import Sequence

from scieqlint.config.model import Config
from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import Diagnostic, SourceSpan
from scieqlint.facts.reference import EquationLabelFact, EquationRefFact
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost
from scieqlint.scan.base import (
    EquationLabel,
    EquationReference,
    LabelSource,
    ReferenceSource,
)
from scieqlint.scan.latex import LatexScanner

SOURCE_REFERENCE_KINDS = {
    ReferenceSource.MYST_EQ_ROLE: "eq",
    ReferenceSource.MYST_NUMREF_ROLE: "numref",
    ReferenceSource.LATEX_REF: "tex-ref",
    ReferenceSource.LATEX_EQREF: "tex-eqref",
}


def without_profile_owned_legacy_reference_diagnostics(
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
            and span_is_within_any(diagnostic.span, owned_spans)
        )
    ]


def span_is_within_any(span: SourceSpan, containers: Sequence[SourceSpan]) -> bool:
    """Return whether a fact span belongs to one of the source-owned ranges."""

    return any(
        container.path == span.path
        and container.cell == span.cell
        and container.start <= span.start
        and span.end <= container.end
        for container in containers
    )


def raw_missing_label_diagnostics(
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


def source_label_facts(
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
            legacy_equation_label_fact(label)
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
            fact_id=source_role_fact_id(label.span, "source-label"),
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


def source_reference_facts(
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
            legacy_equation_reference_fact(reference)
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
        ref_kind = SOURCE_REFERENCE_KINDS[reference.source]
        target = reference.target.strip()
        facts.append(
            EquationRefFact(
                fact_id=source_role_fact_id(reference.span, "source-reference"),
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


def source_role_fact_id(span: SourceSpan, role: str) -> str:
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


def _legacy_span_identity(span: SourceSpan) -> str:
    cell = "" if span.cell is None else f"::cell-{span.cell}"
    return f"{span.start}:{span.end}{cell}"


def legacy_equation_label_fact(label: EquationLabel) -> EquationLabelFact:
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


def legacy_equation_reference_fact(reference: EquationReference) -> EquationRefFact:
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
