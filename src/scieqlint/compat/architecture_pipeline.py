"""Compatibility entry point for the architecture implementation slice.

This is intentionally a parallel entry point. Existing `check_paths()` behavior
can keep using the v0.1 scanner/checker stack until individual PRs migrate it.
"""

from __future__ import annotations

from collections.abc import Sequence

from scieqlint.compat.generated import attach_generated_provenance
from scieqlint.diag.ir import DiagnosticIR
from scieqlint.engine.base import Engine
from scieqlint.engine.generated import GeneratedOutputEngine
from scieqlint.engine.math_container import MathContainerEngine
from scieqlint.engine.portability import PortabilityEngine
from scieqlint.engine.project import ProjectGraphEngine
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.engine.structure import StructureEngine
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import SourceDocument
from scieqlint.math.host import MathHost
from scieqlint.policy.host import PolicyHost
from scieqlint.query.host import QueryHost
from scieqlint.schema.result import AnalysisResult

_ENGINES: dict[str, Engine] = {
    "structure": StructureEngine(),
    "references": ReferenceEngine(),
    "generated": GeneratedOutputEngine(),
    "math-container": MathContainerEngine(),
    "project": ProjectGraphEngine(),
    "portability": PortabilityEngine(),
}


def analyze_documents_architecture(
    documents: Sequence[SourceDocument],
    *,
    profiles: tuple[str, ...] = ("scientific-myst",),
    generated_pairs: tuple[tuple[str, str], ...] = (),
) -> AnalysisResult:
    policy = PolicyHost()
    plan = policy.make_plan(profiles)
    snapshot = MySTFrontend().lower(documents)
    if generated_pairs:
        snapshot = attach_generated_provenance(snapshot, generated_pairs)
    snapshot = MathHost().classify(snapshot)
    query = QueryHost(snapshot)
    diagnostics_ir: list[DiagnosticIR] = []
    for name in sorted(plan.engines):
        engine = _ENGINES.get(name)
        if engine is None:
            continue
        diagnostics_ir.extend(engine.run(query))
    diagnostics = policy.apply(tuple(diagnostics_ir), plan)
    return AnalysisResult(snapshot=snapshot, diagnostics=diagnostics, profiles=profiles)
