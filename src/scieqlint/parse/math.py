"""MathHost façade for frontend-produced math candidates."""

from __future__ import annotations

from dataclasses import replace

from scieqlint.facts.math import DisplayMathFact, InlineMathFact, UnknownMathFact
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.markdown import is_non_math_tex_environment
from scieqlint.source.maps import SourceMap

from . import math_classification as _classification
from .generated_formulas import classify_generated_formulas as _classify_generated_formulas
from .macro_facts import inline_math_macro_facts as _inline_math_macro_facts
from .raw_equations import raw_equation_facts as _raw_equation_facts
from .typst_portability import typst_math_risks as _typst_math_risks

_classify_display = _classification.classify_display
_classify_inline = _classification.classify_inline
_has_missing_required_argument = _classification.has_missing_required_argument


class MathHost:
    """Classify inline math after the frontend has preserved source identity."""

    def classify(self, snapshot: FactSnapshot) -> FactSnapshot:
        inline_math: list[InlineMathFact] = []
        unknown_math: list[UnknownMathFact] = []
        existing_unknown_ids = {fact.source_math_fact_id for fact in snapshot.unknown_math}
        for fact in snapshot.inline_math:
            status, unknown = _classify_inline(fact)
            inline_math.append(replace(fact, parse_status=status))
            if unknown is not None and fact.fact_id not in existing_unknown_ids:
                unknown_math.append(unknown)
        display_math: list[DisplayMathFact] = []
        equation_labels = list(snapshot.equation_labels)
        equation_refs = list(snapshot.equation_refs)
        existing_label_ids = {fact.fact_id for fact in equation_labels}
        existing_ref_ids = {fact.fact_id for fact in equation_refs}
        raw_display_ids = {
            fact.fact_id for fact in snapshot.display_math if fact.container == "raw-latex"
        }
        source_maps = {
            document.path.as_posix(): SourceMap.for_document(document)
            for document in snapshot.documents
        }
        for fact in snapshot.display_math:
            if fact.container == "raw-latex" and is_non_math_tex_environment(fact.environment):
                continue
            display, unknown = _classify_display(fact)
            if (
                fact.container == "raw-latex"
                and fact.complete
                and not is_non_math_tex_environment(fact.environment)
            ):
                labels, references = _raw_equation_facts(
                    display,
                    source_maps[fact.document_id],
                )
                display = replace(
                    display,
                    label_fact_ids=tuple(label.fact_id for label in labels),
                )
                for label in labels:
                    if label.fact_id in existing_label_ids:
                        continue
                    equation_labels.append(label)
                    existing_label_ids.add(label.fact_id)
                for reference in references:
                    if reference.fact_id in existing_ref_ids:
                        continue
                    equation_refs.append(reference)
                    existing_ref_ids.add(reference.fact_id)
            display_math.append(display)
            if unknown is not None and fact.fact_id not in existing_unknown_ids:
                unknown_math.append(unknown)
        macro_declarations, macro_uses = _inline_math_macro_facts(
            snapshot.documents,
            tuple(inline_math),
        )
        classified = replace(
            snapshot,
            inline_math=tuple(inline_math),
            display_math=tuple(display_math),
            equation_labels=tuple(equation_labels),
            equation_refs=tuple(equation_refs),
            math_macro_declarations=macro_declarations,
            math_macro_uses=macro_uses,
            unknown_math=(*snapshot.unknown_math, *unknown_math),
        )
        accepted_raw_display_ids = {
            fact.fact_id
            for fact in display_math
            if fact.fact_id in raw_display_ids and fact.container == "ams"
        }
        return replace(
            classified,
            generated_formulas=tuple(
                formula
                for formula in _classify_generated_formulas(classified)
                if not (
                    formula.source_math_fact_id in raw_display_ids
                    and formula.source_math_fact_id not in accepted_raw_display_ids
                )
            ),
        )

    def typst_portability(
        self,
        snapshot: FactSnapshot,
    ) -> tuple[OutputPortabilityFact, ...]:
        """Classify source math forms whose semantics need Typst review."""

        return _typst_math_risks(snapshot)
