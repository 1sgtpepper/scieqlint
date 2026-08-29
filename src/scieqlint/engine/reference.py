"""Reference diagnostics over ``ReferenceQueryView``."""

from __future__ import annotations

from typing import cast

from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.ir import DiagnosticIR
from scieqlint.facts.reference import (
    EquationLabelFact,
    EquationRefFact,
    GenericRefFact,
    NormalizedReferenceTarget,
    format_member_target_identity,
    normalized_reference_target,
)
from scieqlint.query.host import QueryHost

_METADATA_PREVIEW_MAX_CHARS = 256


class ReferenceEngine:
    name = "references"

    def __init__(self, *, profile: str | None = None) -> None:
        self.profile = profile

    rule_codes = frozenset(
        {
            "REF001",
            "REF002",
            "REF004",
            "REF005",
            "REF006",
            "REF007",
            "REF008",
            "REF009",
            "REF010",
            "REF011",
        }
    )

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
        duplicate_cell_info = CATALOG["REF010"]
        target_index = query.references.target_identity_index()
        for target, duplicates in sorted(
            query.references.duplicate_code_cell_targets().items(),
            key=lambda item: (item[0][0].as_posix(), item[0][1]),
        ):
            facts = tuple(sorted(target_index[target], key=lambda fact: fact.fact_id))
            target_label = target[1]
            for duplicate in duplicates:
                diagnostics.append(
                    DiagnosticIR(
                        code=duplicate_cell_info.code,
                        severity_default=duplicate_cell_info.severity,
                        message=f"{duplicate_cell_info.message}: {target_label}",
                        span=duplicate.label_span or duplicate.span,
                        rule="references.code_cell_target",
                        false_positive_risk="low",
                        provenance_ids=tuple(fact.fact_id for fact in facts),
                        properties=(
                            ("target", format_member_target_identity(target)),
                            ("target_count", str(len(facts))),
                        ),
                    )
                )
        nonvisible_impacts = query.references.nonvisible_equation_target_impacts()
        nonvisible_only_reference_ids = {
            impact.reference.fact_id
            for impact in nonvisible_impacts
            if not impact.visible_targets and (impact.hidden_targets or impact.excluded_targets)
        }
        missing_equation_info = CATALOG["REF002"]
        for ref in sorted(
            query.references.unresolved_equation_refs(),
            key=_fact_source_key,
        ):
            if ref.fact_id in nonvisible_only_reference_ids:
                continue
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
        for impact in sorted(
            nonvisible_impacts,
            key=lambda item: _fact_source_key(item.reference),
        ):
            ref = impact.reference
            hidden_example = impact.hidden_targets[0] if impact.hidden_targets else None
            excluded_example = impact.excluded_targets[0] if impact.excluded_targets else None
            hidden_suffix = f" (example={hidden_example.document_id!r})" if hidden_example else ""
            excluded_suffix = (
                f" (example={excluded_example.document_id!r})" if excluded_example else ""
            )
            provenance_ids = (ref.fact_id,)
            properties = (
                ("target", ref.normalized_target),
                ("visible_target_count", str(len(impact.visible_targets))),
                ("hidden_target_count", str(len(impact.hidden_targets))),
                ("excluded_target_count", str(len(impact.excluded_targets))),
            )
            if hidden_example is not None:
                provenance_ids += (hidden_example.fact_id,)
                properties += (("hidden_example_document", hidden_example.document_id),)
            if excluded_example is not None:
                provenance_ids += (excluded_example.fact_id,)
                properties += (("excluded_example_document", excluded_example.document_id),)
            diagnostics.append(
                DiagnosticIR(
                    code=nonvisible_info.code,
                    severity_default=nonvisible_info.severity,
                    message=f"{nonvisible_info.message}: {ref.target}",
                    span=ref.target_span or ref.span,
                    detail=(
                        f"visible targets={len(impact.visible_targets)}; "
                        f"hidden targets={len(impact.hidden_targets)}{hidden_suffix}; "
                        f"excluded targets={len(impact.excluded_targets)}{excluded_suffix}"
                    ),
                    hint=(
                        "Rename the non-visible target or make its source visible in "
                        "the rendered project."
                    ),
                    rule="references.nonvisible_equation_target",
                    false_positive_risk="low",
                    provenance_ids=provenance_ids,
                    properties=properties,
                )
            )
        if self.profile == "reference-display":
            display_info = CATALOG["REF009"]
            for issue in query.references.unclear_nonheading_display_text():
                fact = issue.fact
                rendered = fact.explicit_text if fact.explicit_text is not None else ""
                target_identity = format_member_target_identity(
                    cast(NormalizedReferenceTarget, fact.target_identity)
                )
                target_type = cast(str, fact.target_type)
                diagnostics.append(
                    DiagnosticIR(
                        code=display_info.code,
                        severity_default=display_info.severity,
                        message=f"{display_info.message}: {fact.normalized_target}",
                        span=fact.display_text_span or fact.span,
                        detail=(
                            f"target_type={target_type!r}; "
                            f"reference_kind={fact.reference_kind!r}; "
                            f"display_text={rendered!r}; reason={issue.reason!r}"
                        ),
                        hint="Provide descriptive display text for this non-heading target.",
                        rule="references.display_text",
                        profile_gated=True,
                        false_positive_risk="medium",
                        profile=self.profile,
                        provenance_ids=(fact.source_fact_id, fact.fact_id, *fact.target_fact_ids),
                        properties=(
                            ("target", target_identity),
                            ("target_type", target_type),
                            ("reference_kind", fact.reference_kind),
                            ("display_intent", fact.display_intent),
                            ("display_text", rendered),
                            ("reason", issue.reason),
                        ),
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
            canonical_metadata_preview = _metadata_preview(canonical_metadata)
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
                            f"metadata={_metadata_preview(fact_metadata)}; "
                            f"canonical boundary {canonical.output_boundary!r} reports "
                            f"kind={canonical_kind!r}, "
                            f"format={canonical.source_format!r}, "
                            f"metadata={canonical_metadata_preview}"
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
                        ("target", format_member_target_identity(identity)),
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


def _metadata_preview(metadata: tuple[tuple[str, str], ...]) -> str:
    raw_chars = sum(len(key) + len(value) for key, value in metadata)
    if raw_chars <= _METADATA_PREVIEW_MAX_CHARS:
        rendered = repr(dict(metadata))
        if len(rendered) <= _METADATA_PREVIEW_MAX_CHARS:
            return rendered

    key, value = metadata[0]
    omitted = len(metadata) - 1
    suffix = f", ... <{omitted} entries omitted>" if omitted else ""
    return f"{{{_metadata_atom_preview(key)}: {_metadata_atom_preview(value)}{suffix}}}"


def _metadata_atom_preview(value: str) -> str:
    if len(value) > 64:
        return f"<{len(value)} chars>"
    rendered = repr(value)
    return rendered if len(rendered) <= 80 else f"<{len(value)} chars>"


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
