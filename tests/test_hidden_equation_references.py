from __future__ import annotations

import json
from pathlib import PurePosixPath

from scieqlint.diag.model import CheckResult, Severity, SourceSpan
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.facts.reference import EquationLabelFact, EquationRefFact, TargetVisibility
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.query.host import QueryHost
from scieqlint.report.json import JsonReporter


def span(path: str, start: int) -> SourceSpan:
    return SourceSpan(
        path=PurePosixPath(path),
        start=start,
        end=start + 4,
        line=1,
        col=start + 1,
        end_line=1,
        end_col=start + 5,
    )


def label(
    fact_id: str,
    *,
    document: str,
    visibility: TargetVisibility = "visible",
    target: str = "eq-energy",
    start: int = 0,
) -> EquationLabelFact:
    target_span = span(document, start)
    return EquationLabelFact(
        fact_id=fact_id,
        document_id=document,
        span=target_span,
        raw=target,
        label=target,
        normalized_label=target,
        label_syntax_kind="myst-directive-option",
        source_block_id=f"{fact_id}-math",
        visibility=visibility,
        label_span=target_span,
    )


def reference(
    fact_id: str = "ref",
    *,
    target: str = "eq-energy",
    start: int = 20,
    visibility: TargetVisibility = "visible",
    document: str = "paper.md",
) -> EquationRefFact:
    target_span = span(document, start)
    return EquationRefFact(
        fact_id=fact_id,
        document_id=document,
        span=target_span,
        raw=f"{{eq}}`{target}`",
        ref_kind="eq",
        target=target,
        normalized_target=target,
        visibility=visibility,
        target_span=target_span,
        role_span=target_span,
    )


def test_visible_hidden_and_excluded_equation_targets_remain_separate() -> None:
    visible = label("visible", document="paper.md")
    hidden = label("hidden", document="appendix.md", visibility="hidden")
    excluded = label("excluded", document="draft.md", visibility="excluded")
    ref = reference()
    query = QueryHost(
        FactSnapshot(
            equation_labels=(visible, hidden, excluded),
            equation_refs=(ref,),
        )
    )

    assert query.references.equation_targets() == (visible, hidden, excluded)
    assert query.references.visible_equation_targets() == (visible,)
    assert query.references.hidden_equation_targets() == (hidden,)
    assert query.references.excluded_equation_targets() == (excluded,)
    assert query.references.equation_target_index() == {"eq-energy": (visible,)}
    assert query.references.hidden_equation_target_index() == {"eq-energy": (hidden,)}
    assert query.references.excluded_equation_target_index() == {"eq-energy": (excluded,)}
    assert query.references.target_index()["eq-energy"] == (visible,)
    assert query.references.duplicate_equation_targets() == {}
    assert query.references.unresolved_equation_refs() == ()

    [impact] = query.references.nonvisible_equation_target_impacts()
    assert impact.reference is ref
    assert impact.visible_targets == (visible,)
    assert impact.hidden_targets == (hidden,)
    assert impact.excluded_targets == (excluded,)


def test_reference_engine_reports_one_nonvisible_resolution_impact_per_reference() -> None:
    visible = label("visible", document="paper.md")
    hidden = label("hidden", document="appendix.md", visibility="hidden")
    excluded = label("excluded", document="draft.md", visibility="excluded")
    ref = reference()

    diagnostics = ReferenceEngine().run(
        QueryHost(
            FactSnapshot(
                equation_labels=(visible, hidden, excluded),
                equation_refs=(ref,),
            )
        )
    )

    assert [diagnostic.code for diagnostic in diagnostics] == ["REF008"]
    [diagnostic] = diagnostics
    assert diagnostic.severity_default is Severity.WARNING
    assert diagnostic.span == ref.target_span
    assert diagnostic.message == (
        "equation reference matches a hidden or excluded target: eq-energy"
    )
    assert diagnostic.detail == (
        "visible targets=1; hidden targets=['appendix.md']; excluded targets=['draft.md']"
    )
    assert diagnostic.provenance_ids == ("ref", "hidden", "excluded")
    assert dict(diagnostic.properties) == {
        "target": "eq-energy",
        "visible_target_count": "1",
        "hidden_target_count": "1",
        "excluded_target_count": "1",
        "hidden_documents": "appendix.md",
        "excluded_documents": "draft.md",
    }

    payload = json.loads(
        JsonReporter().render(
            CheckResult(
                diagnostics=(diagnostic.to_diagnostic(),),
                files_checked=3,
                math_blocks_checked=1,
                config_path=None,
                version="test",
            )
        )
    )
    projected = payload["diagnostics"][0]
    assert projected["code"] == "REF008"
    assert projected["provenance_ids"] == ["ref", "hidden", "excluded"]
    assert projected["properties"]["hidden_documents"] == "appendix.md"


def test_hidden_only_target_remains_unresolved_and_reports_visibility_impact() -> None:
    hidden = label("hidden", document="appendix.md", visibility="hidden")
    ref = reference()

    diagnostics = ReferenceEngine().run(
        QueryHost(FactSnapshot(equation_labels=(hidden,), equation_refs=(ref,)))
    )

    assert [diagnostic.code for diagnostic in diagnostics] == ["REF002", "REF008"]
    assert diagnostics[1].provenance_ids == ("ref", "hidden")
    assert dict(diagnostics[1].properties)["visible_target_count"] == "0"


def test_hidden_equation_references_are_not_checked_against_any_target_visibility() -> None:
    visible = label("visible", document="target.md", target="eq-visible")
    hidden = label("hidden", document="target.md", visibility="hidden", target="eq-hidden")

    assert ReferenceEngine().run(
        QueryHost(
            FactSnapshot(
                equation_labels=(visible,),
                equation_refs=(
                    reference(
                        target="eq-visible",
                        visibility="hidden",
                        document="source.md",
                    ),
                ),
            )
        )
    ) == ()
    assert ReferenceEngine().run(
        QueryHost(
            FactSnapshot(
                equation_labels=(hidden,),
                equation_refs=(
                    reference(
                        target="eq-hidden",
                        visibility="hidden",
                        document="source.md",
                    ),
                ),
            )
        )
    ) == ()
    assert ReferenceEngine().run(
        QueryHost(
            FactSnapshot(
                equation_refs=(
                    reference(
                        target="eq-missing",
                        visibility="hidden",
                        document="source.md",
                    ),
                )
            )
        )
    ) == ()

    visible_missing = ReferenceEngine().run(
        QueryHost(
            FactSnapshot(
                equation_refs=(reference(target="eq-missing", document="source.md"),)
            )
        )
    )
    assert [diagnostic.code for diagnostic in visible_missing] == ["REF002"]


def test_nonvisible_labels_without_matching_references_do_not_warn() -> None:
    hidden = label(
        "hidden",
        document="appendix.md",
        visibility="hidden",
        target="eq-hidden",
    )
    excluded = label(
        "excluded",
        document="draft.md",
        visibility="excluded",
        target="eq-draft",
    )

    query = QueryHost(FactSnapshot(equation_labels=(hidden, excluded)))

    assert query.references.nonvisible_equation_target_impacts() == ()
    assert ReferenceEngine().run(query) == ()


def test_nonvisible_target_provenance_is_stable_under_shuffled_fact_input() -> None:
    earlier = label(
        "hidden-a",
        document="a.md",
        visibility="hidden",
        start=8,
    )
    later = label(
        "hidden-b",
        document="b.md",
        visibility="hidden",
        start=2,
    )
    ref = reference()

    first = ReferenceEngine().run(
        QueryHost(FactSnapshot(equation_labels=(later, earlier), equation_refs=(ref,)))
    )
    second = ReferenceEngine().run(
        QueryHost(FactSnapshot(equation_labels=(earlier, later), equation_refs=(ref,)))
    )

    assert first == second
    assert first[-1].provenance_ids == ("ref", "hidden-a", "hidden-b")
    assert dict(first[-1].properties)["hidden_documents"] == "a.md,b.md"


def test_visible_duplicate_behavior_and_default_visibility_are_unchanged() -> None:
    first = label("visible-a", document="a.md")
    second = label("visible-b", document="b.md")
    ref = reference()

    diagnostics = ReferenceEngine().run(
        QueryHost(FactSnapshot(equation_labels=(first, second), equation_refs=(ref,)))
    )

    assert first.visibility == "visible"
    assert [diagnostic.code for diagnostic in diagnostics] == ["REF001"]
    assert diagnostics[0].span == second.label_span
