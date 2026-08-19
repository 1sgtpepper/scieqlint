"""Reference diagnostics over ``ReferenceQueryView``."""

from __future__ import annotations

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.ir import DiagnosticIR
from scieqlint.facts.reference import EquationLabelFact, EquationRefFact
from scieqlint.query.host import QueryHost


class ReferenceEngine:
    name = "references"
    rule_codes = frozenset(
        {"REF001", "REF002", "REF004", "REF005", "REF006", "REF007", "REF008", "REF011"}
    )

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        diagnostics: list[DiagnosticIR] = []
        duplicate_equation_info = CATALOG["REF001"]
        duplicate_targets = query.references.duplicate_equation_targets().values()
        for same_name in sorted(duplicate_targets, key=lambda facts: _fact_source_key(facts[0])):
            for duplicate in sorted(same_name, key=_fact_source_key)[1:]:
                diagnostics.append(
                    DiagnosticIR(
                        code=duplicate_equation_info.code,
                        severity_default=duplicate_equation_info.severity,
                        message=(f"{duplicate_equation_info.message}: {duplicate.label}"),
                        span=duplicate.label_span or duplicate.span,
                        rule="references",
                        false_positive_risk="low",
                    )
                )
        missing_equation_info = CATALOG["REF002"]
        for ref in query.references.unresolved_equation_refs():
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
        nonvisible_info = CATALOG["REF008"]
        for impact in query.references.nonvisible_equation_target_impacts():
            ref = impact.reference
            hidden_documents = tuple(
                dict.fromkeys(label.document_id for label in impact.hidden_targets)
            )
            excluded_documents = tuple(
                dict.fromkeys(label.document_id for label in impact.excluded_targets)
            )
            diagnostics.append(
                DiagnosticIR(
                    code=nonvisible_info.code,
                    severity_default=nonvisible_info.severity,
                    message=f"{nonvisible_info.message}: {ref.target}",
                    span=ref.target_span or ref.span,
                    detail=(
                        f"visible targets={len(impact.visible_targets)}; "
                        f"hidden targets={list(hidden_documents)!r}; "
                        f"excluded targets={list(excluded_documents)!r}"
                    ),
                    hint=(
                        "Rename the non-visible target or make its source visible in "
                        "the rendered project."
                    ),
                    rule="references.nonvisible_equation_target",
                    false_positive_risk="low",
                    provenance_ids=(
                        ref.fact_id,
                        *(label.fact_id for label in impact.hidden_targets),
                        *(label.fact_id for label in impact.excluded_targets),
                    ),
                    properties=(
                        ("target", ref.normalized_target),
                        ("visible_target_count", str(len(impact.visible_targets))),
                        ("hidden_target_count", str(len(impact.hidden_targets))),
                        ("excluded_target_count", str(len(impact.excluded_targets))),
                        ("hidden_documents", ",".join(hidden_documents)),
                        ("excluded_documents", ",".join(excluded_documents)),
                    ),
                )
            )
        missing_info = CATALOG["REF004"]
        for ref in query.references.unresolved_generic_refs():
            if ref.role_kind != "ref":
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
            canonical = facts[0]
            canonical_kind = canonical.resolved_target_kind or canonical.reference_kind
            canonical_metadata = canonical.target_metadata or canonical.display_metadata
            canonical_signature = (canonical_kind, tuple(sorted(canonical_metadata)))
            for fact in facts:
                fact_kind = fact.resolved_target_kind or fact.reference_kind
                fact_metadata = fact.target_metadata or fact.display_metadata
                signature = (fact_kind, tuple(sorted(fact_metadata)))
                if signature == canonical_signature:
                    continue
                diagnostics.append(
                    DiagnosticIR(
                        code=metadata_info.code,
                        severity_default=metadata_info.severity,
                        message=f"{metadata_info.message}: {target}",
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
                            ("target", target),
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
        for (
            ref,
            raw_matches,
            normalized_matches,
        ) in query.references.path_normalization_mismatches():
            assert ref.resolved_raw_target_path is not None
            assert ref.normalized_target_path is not None
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
                        ("raw_path", ref.resolved_raw_target_path),
                        ("normalized_path", ref.normalized_target_path.as_posix()),
                        ("raw_match_count", str(len(raw_matches))),
                        ("normalized_match_count", str(len(normalized_matches))),
                    ),
                )
            )
        ambiguous_info = CATALOG["REF005"]
        for ref in query.references.ambiguous_generic_refs():
            if ref.role_kind != "ref":
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
        return tuple(diagnostics)


def _fact_source_key(
    fact: EquationLabelFact | EquationRefFact,
) -> tuple[str, int, int, str]:
    span = fact.label_span if isinstance(fact, EquationLabelFact) else fact.target_span or fact.span
    return (
        fact.document_id,
        -1 if span is None else span.start,
        -1 if span is None else span.end,
        fact.fact_id,
    )
