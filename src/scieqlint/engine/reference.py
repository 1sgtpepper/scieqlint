"""Reference diagnostics over ``ReferenceQueryView``."""

from __future__ import annotations

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.ir import DiagnosticIR
from scieqlint.facts.reference import (
    EquationLabelFact,
    EquationRefFact,
    GenericRefFact,
    format_member_target_identity,
    normalized_reference_target,
)
from scieqlint.query.host import QueryHost


class ReferenceEngine:
    name = "references"
    rule_codes = frozenset({"REF001", "REF002", "REF004", "REF005", "REF006", "REF007", "REF011"})

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        diagnostics: list[DiagnosticIR] = []
        duplicate_equation_info = CATALOG["REF001"]
        duplicate_targets = query.references.duplicate_equation_targets().values()
        duplicate_groups = tuple(
            sorted(
                (tuple(sorted(same_name, key=_fact_source_key)) for same_name in duplicate_targets),
                key=lambda facts: _fact_source_key(facts[0]),
            )
        )
        for same_name in duplicate_groups:
            for duplicate in same_name[1:]:
                diagnostics.append(
                    DiagnosticIR(
                        code=duplicate_equation_info.code,
                        severity_default=duplicate_equation_info.severity,
                        message=f"{duplicate_equation_info.message}: {duplicate.normalized_label}",
                        span=duplicate.label_span or duplicate.span,
                        rule="references",
                        false_positive_risk="low",
                    )
                )
        missing_equation_info = CATALOG["REF002"]
        for ref in sorted(
            query.references.unresolved_equation_refs(),
            key=_fact_source_key,
        ):
            diagnostics.append(
                DiagnosticIR(
                    code=missing_equation_info.code,
                    severity_default=missing_equation_info.severity,
                    message=f"{missing_equation_info.message}: {ref.target}",
                    span=ref.target_span or ref.span,
                    detail=f"reference text: {ref.raw}",
                    rule="references",
                    false_positive_risk="low",
                )
            )
        ambiguous_equation_info = CATALOG["REF011"]
        for ref in sorted(
            query.references.ambiguous_equation_refs(),
            key=_fact_source_key,
        ):
            diagnostics.append(
                DiagnosticIR(
                    code=ambiguous_equation_info.code,
                    severity_default=ambiguous_equation_info.severity,
                    message=f"{ambiguous_equation_info.message}: {ref.target}",
                    span=ref.target_span or ref.span,
                    detail=f"reference text: {ref.raw}",
                    rule="references.equation_target_ambiguous",
                    false_positive_risk="low",
                )
            )
        missing_info = CATALOG["REF004"]
        equation_missing_info = CATALOG["REF002"]
        for ref in sorted(
            query.references.unresolved_generic_refs(),
            key=_fact_source_key,
        ):
            if ref.role_kind == "markdown-link" and ref.raw_target_path is None:
                diagnostics.append(
                    DiagnosticIR(
                        code=equation_missing_info.code,
                        severity_default=equation_missing_info.severity,
                        message=f"{equation_missing_info.message}: {ref.target}",
                        span=ref.target_span or ref.span,
                        detail=f"reference text: {ref.raw}",
                        rule="references",
                        false_positive_risk="low",
                    )
                )
                continue
            if ref.role_kind not in {"ref", "markdown-link"}:
                continue
            diagnostics.append(
                DiagnosticIR(
                    code=missing_info.code,
                    severity_default=missing_info.severity,
                    message=f"{missing_info.message}: {ref.target}",
                    span=ref.target_span or ref.span,
                    detail=f"reference text: {ref.raw}",
                    rule="references.generic_target",
                    false_positive_risk="low",
                )
            )
        metadata_info = CATALOG["REF007"]
        for target, facts in query.references.conflicting_metadata():
            display_target = format_member_target_identity(target)
            canonical = facts[0]
            canonical_kind = canonical.resolved_target_kind
            canonical_metadata = canonical.target_metadata
            canonical_signature = (canonical_kind, tuple(sorted(canonical_metadata)))
            for fact in facts:
                fact_kind = fact.resolved_target_kind
                fact_metadata = fact.target_metadata
                signature = (fact_kind, tuple(sorted(fact_metadata)))
                if signature == canonical_signature:
                    continue
                diagnostics.append(
                    DiagnosticIR(
                        code=metadata_info.code,
                        severity_default=metadata_info.severity,
                        message=f"{metadata_info.message}: {display_target}",
                        span=fact.target_span or fact.span,
                        detail=(
                            f"{fact.output_boundary!r} reports "
                            f"kind={fact_kind!r}, "
                            f"format={fact.source_format!r}, "
                            f"metadata={dict(fact_metadata)!r}; "
                            f"canonical boundary {canonical.output_boundary!r} reports "
                            f"kind={canonical_kind!r}, "
                            f"format={canonical.source_format!r}, "
                            f"metadata={dict(canonical_metadata)!r}"
                        ),
                        hint="Use consistent cross-reference metadata for this target.",
                        rule="references.crossref_metadata_conflict",
                        false_positive_risk="low",
                        provenance_ids=(canonical.fact_id, fact.fact_id),
                        properties=(
                            ("target", display_target),
                            ("output_boundary", fact.output_boundary),
                            ("resolved_target_kind", fact_kind or ""),
                            ("source_format", fact.source_format),
                            ("canonical_boundary", canonical.output_boundary),
                            ("canonical_resolved_target_kind", canonical_kind or ""),
                            ("canonical_source_format", canonical.source_format),
                        ),
                    )
                )
        normalized_path_info = CATALOG["REF006"]
        for ref, raw_matches, normalized_matches in sorted(
            query.references.path_normalization_mismatches(),
            key=lambda item: _fact_source_key(item[0]),
        ):
            assert ref.resolved_raw_target_path is not None
            assert ref.normalized_target_path is not None
            identity = normalized_reference_target(ref)
            diagnostics.append(
                DiagnosticIR(
                    code=normalized_path_info.code,
                    severity_default=normalized_path_info.severity,
                    message=(f"{normalized_path_info.message}: {ref.resolved_raw_target_path}"),
                    span=ref.target_span or ref.span,
                    detail=(
                        f"raw matches={list(raw_matches)!r}; normalized "
                        f"{ref.normalized_target_path.as_posix()!r} "
                        f"matches={list(normalized_matches)!r}"
                    ),
                    hint="Use the normalized project-relative path spelling.",
                    rule="references.project_path_normalization",
                    false_positive_risk="low",
                    properties=(
                        ("target", f"{identity[0].as_posix()}#{identity[1]}"),
                        ("raw_path", ref.resolved_raw_target_path),
                        ("normalized_path", ref.normalized_target_path.as_posix()),
                        ("raw_match_count", str(len(raw_matches))),
                        ("normalized_match_count", str(len(normalized_matches))),
                    ),
                )
            )
        ambiguous_info = CATALOG["REF005"]
        for ref in sorted(
            query.references.ambiguous_generic_refs(),
            key=_fact_source_key,
        ):
            if ref.role_kind not in {"ref", "markdown-link"}:
                continue
            diagnostics.append(
                DiagnosticIR(
                    code=ambiguous_info.code,
                    severity_default=ambiguous_info.severity,
                    message=f"{ambiguous_info.message}: {ref.target}",
                    span=ref.target_span or ref.span,
                    detail=f"reference text: {ref.raw}",
                    rule="references.generic_target_ambiguous",
                    false_positive_risk="low",
                )
            )
        return tuple(sorted(diagnostics, key=_diagnostic_key))


def _fact_source_key(
    fact: EquationLabelFact | EquationRefFact | GenericRefFact,
) -> tuple[str, int, int, int, str, str]:
    span = (
        fact.label_span or fact.span
        if isinstance(fact, EquationLabelFact)
        else fact.target_span or fact.span
    )
    return (
        fact.document_id,
        -1 if span is None or span.cell is None else span.cell,
        -1 if span is None else span.start,
        -1 if span is None else span.end,
        fact.fact_id,
        fact.raw or "",
    )


def _diagnostic_key(
    diagnostic: DiagnosticIR,
) -> tuple[str, int, int, int, str, str, str, str, str]:
    span = diagnostic.span
    return (
        "" if span is None else span.path.as_posix(),
        -1 if span is None or span.cell is None else span.cell,
        -1 if span is None else span.start,
        -1 if span is None else span.end,
        diagnostic.code,
        diagnostic.message,
        diagnostic.detail or "",
        diagnostic.rule or "",
        diagnostic.hint or "",
    )
