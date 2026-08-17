"""Reference diagnostics over ``ReferenceQueryView``."""

from __future__ import annotations

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.ir import DiagnosticIR
from scieqlint.query.host import QueryHost


class ReferenceEngine:
    name = "references"
    rule_codes = frozenset({"REF001", "REF002", "REF004", "REF005", "REF006", "REF007"})

    def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
        diagnostics: list[DiagnosticIR] = []
        duplicate_equation_info = CATALOG["REF001"]
        for same_name in query.references.duplicate_equation_targets().values():
            for duplicate in same_name[1:]:
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
            canonical_signature = (
                canonical.reference_kind,
                tuple(sorted(canonical.display_metadata)),
            )
            for fact in facts:
                signature = (
                    fact.reference_kind,
                    tuple(sorted(fact.display_metadata)),
                )
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
                            f"kind={fact.reference_kind!r}, "
                            f"format={fact.source_format!r}, "
                            f"display={dict(fact.display_metadata)!r}; "
                            f"canonical boundary {canonical.output_boundary!r} reports "
                            f"kind={canonical.reference_kind!r}, "
                            f"format={canonical.source_format!r}, "
                            f"display={dict(canonical.display_metadata)!r}"
                        ),
                        hint="Use consistent cross-reference metadata for this target.",
                        rule="references.crossref_metadata_conflict",
                        false_positive_risk="low",
                        provenance_ids=(canonical.fact_id, fact.fact_id),
                        properties=(
                            ("target", target),
                            ("output_boundary", fact.output_boundary),
                            ("reference_kind", fact.reference_kind),
                            ("source_format", fact.source_format),
                            ("canonical_boundary", canonical.output_boundary),
                            ("canonical_reference_kind", canonical.reference_kind),
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
