"""Generated-output QueryView."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.facts.generated import GeneratedFormulaFact, GeneratedProvenanceFact
from scieqlint.facts.reference import TargetAnchorFact
from scieqlint.facts.snapshot import FactSnapshot


@dataclass(frozen=True, slots=True)
class GeneratedOutputQueryView:
    snapshot: FactSnapshot

    def provenance_for_document(self, document_id: str) -> tuple[GeneratedProvenanceFact, ...]:
        return tuple(
            provenance
            for provenance in self.snapshot.generated_provenance
            if provenance.generated_document_id == document_id
        )

    def suspicious_formula_text(self) -> tuple[GeneratedFormulaFact, ...]:
        return tuple(
            fact
            for fact in self.snapshot.generated_formulas
            if fact.kind in {"spaced-token", "garbled-marker"}
        )

    def bracketed_latex_blocks(self) -> tuple[GeneratedFormulaFact, ...]:
        return tuple(
            fact for fact in self.snapshot.generated_formulas if fact.kind == "bracketed-block"
        )

    def formula_placeholders(self) -> tuple[GeneratedFormulaFact, ...]:
        return tuple(
            fact
            for fact in self.snapshot.generated_formulas
            if fact.kind in {"placeholder", "empty-display", "image-placeholder"}
        )

    def equation_like_text_items(self) -> tuple[GeneratedFormulaFact, ...]:
        return tuple(
            fact for fact in self.snapshot.generated_formulas if fact.kind == "equation-like-text"
        )

    def dropped_targets(self) -> tuple[tuple[GeneratedProvenanceFact, TargetAnchorFact], ...]:
        facts_by_doc: dict[str, dict[str, TargetAnchorFact]] = {}
        for anchor in self.snapshot.target_anchors:
            facts_by_doc.setdefault(anchor.document_id, {})[anchor.normalized_label] = anchor
        dropped: list[tuple[GeneratedProvenanceFact, TargetAnchorFact]] = []
        for prov in self.snapshot.generated_provenance:
            if prov.source_document_id is None:
                continue
            source_facts = facts_by_doc.get(prov.source_document_id, {})
            source_labels = (
                source_facts.keys()
                & {_normalize_inventory_label(label) for label in prov.preserved_anchor_inventory}
                if prov.preserved_anchor_inventory
                else source_facts.keys()
            )
            generated_facts = facts_by_doc.get(prov.generated_document_id, {})
            for missing in sorted(source_labels - generated_facts.keys()):
                source_fact = source_facts[missing]
                dropped.append((prov, source_fact))
        return tuple(dropped)


def _normalize_inventory_label(label: str) -> str:
    label = label.strip()
    return label[1:] if label.startswith("#") else label
