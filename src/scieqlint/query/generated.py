"""Generated-output QueryView."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.facts.generated import GeneratedFormulaFact, GeneratedProvenanceFact
from scieqlint.facts.reference import TargetAnchorFact
from scieqlint.facts.snapshot import FactSnapshot


@dataclass(frozen=True, slots=True)
class GeneratedOutputQueryView:
    snapshot: FactSnapshot

    def provenance(self) -> tuple[GeneratedProvenanceFact, ...]:
        return self.snapshot.generated_provenance

    def provenance_for_document(self, document_id: str) -> tuple[GeneratedProvenanceFact, ...]:
        return tuple(
            provenance
            for provenance in self.snapshot.generated_provenance
            if provenance.generated_document_id == document_id
        )

    def generated_document_ids(self) -> tuple[str, ...]:
        return tuple(prov.generated_document_id for prov in self.snapshot.generated_provenance)

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

    def dropped_targets(self) -> tuple[tuple[GeneratedProvenanceFact, TargetAnchorFact], ...]:
        anchors_by_doc: dict[str, set[str]] = {}
        facts_by_doc: dict[str, dict[str, TargetAnchorFact]] = {}
        for anchor in self.snapshot.target_anchors:
            anchors_by_doc.setdefault(anchor.document_id, set()).add(anchor.normalized_label)
            facts_by_doc.setdefault(anchor.document_id, {})[anchor.normalized_label] = anchor
        dropped: list[tuple[GeneratedProvenanceFact, TargetAnchorFact]] = []
        for prov in self.snapshot.generated_provenance:
            if prov.source_document_id is None:
                continue
            source_labels = anchors_by_doc.get(prov.source_document_id, set())
            if prov.preserved_anchor_inventory:
                source_labels = source_labels & {
                    _normalize_inventory_label(label) for label in prov.preserved_anchor_inventory
                }
            generated_labels = anchors_by_doc.get(prov.generated_document_id, set())
            for missing in sorted(source_labels - generated_labels):
                source_fact = facts_by_doc[prov.source_document_id][missing]
                dropped.append((prov, source_fact))
        return tuple(dropped)


def _normalize_inventory_label(label: str) -> str:
    label = label.strip()
    return label[1:] if label.startswith("#") else label
