from pathlib import PurePosixPath

from scieqlint.compat.architecture_pipeline import analyze_documents_architecture
from scieqlint.compat.generated import attach_generated_provenance
from scieqlint.engine.algebra import AlgebraEngine
from scieqlint.engine.generated import GeneratedOutputEngine
from scieqlint.facts.math import DisplayMathFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.math.host import MathHost
from scieqlint.query.host import QueryHost


def doc(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def generated_diagnostics(
    documents: tuple[SourceDocument, ...],
    pairs: tuple[tuple[str, str], ...],
):
    snapshot = MySTFrontend().lower(documents)
    snapshot = attach_generated_provenance(snapshot, pairs)
    snapshot = MathHost().classify(snapshot)
    return GeneratedOutputEngine().run(QueryHost(snapshot))


def test_generated_output_reports_dropped_anchor_and_unresolved_ref():
    diagnostics = generated_diagnostics(
        (
            doc("source/jax_intro.md", "(jax_at_workaround)=\n#### A Workaround\n"),
            doc("generated/jax_intro.md", "#### 变通方法\n\nSee {ref}`jax_at_workaround`.\n"),
        ),
        (("source/jax_intro.md", "generated/jax_intro.md"),),
    )

    by_code = {diagnostic.code: diagnostic for diagnostic in diagnostics}
    assert by_code["REF014"].severity_default.value == "error"
    assert by_code["REF014"].related_locations
    assert by_code["GEN003"].severity_default.value == "error"


def test_generated_output_accepts_preserved_anchor_inventory():
    diagnostics = generated_diagnostics(
        (
            doc("source/a.md", "(shared)=\n# Shared\n"),
            doc("generated/a.md", "(shared)=\n# Traducido\n\nSee {ref}`shared`.\n"),
        ),
        (("source/a.md", "generated/a.md"),),
    )

    assert {diagnostic.code for diagnostic in diagnostics}.isdisjoint({"REF014", "GEN003"})


def test_generated_output_reports_suspicious_formula_text():
    diagnostics = generated_diagnostics(
        (
            doc("source/a.md", "$$\nE = mc^2\n$$\n"),
            doc(
                "generated/a.md",
                "\n".join(
                    [
                        "$$",
                        "A t t e n t ( Q , K , V )",
                        "$$",
                        "",
                        "$$",
                        "<!-- formula-not-decoded -->",
                        "$$",
                        "",
                        "$cid:127$",
                    ]
                ),
            ),
        ),
        (("source/a.md", "generated/a.md"),),
    )

    by_code = {diagnostic.code: diagnostic for diagnostic in diagnostics}
    assert by_code["GEN004"].detail == "A t t e n t ( Q , K , V )"
    assert by_code["GEN005"].detail == "<!-- formula-not-decoded -->"
    assert by_code["GEN006"].detail == "cid:127"


def test_generated_formula_checks_ignore_source_documents_when_pairs_are_known():
    diagnostics = generated_diagnostics(
        (
            doc("source/a.md", "$$\nA t t e n t ( Q , K , V )\n$$\n"),
            doc("generated/a.md", "$$\nE = mc^2\n$$\n"),
        ),
        (("source/a.md", "generated/a.md"),),
    )

    assert {diagnostic.code for diagnostic in diagnostics}.isdisjoint(
        {"GEN004", "GEN005", "GEN006"}
    )


def test_architecture_pipeline_surfaces_generated_errors():
    source = doc("source/jax_intro.md", "(jax_at_workaround)=\n#### A Workaround\n")
    generated = doc("generated/jax_intro.md", "#### 变通方法\n\nSee {ref}`jax_at_workaround`.\n")

    result = analyze_documents_architecture(
        (source, generated),
        profiles=("scientific-myst", "generated"),
        generated_pairs=(("source/jax_intro.md", "generated/jax_intro.md"),),
    )

    codes = [diagnostic.code for diagnostic in result.diagnostics]
    assert "REF014" in codes
    assert "GEN003" in codes
    assert any(d.severity.value == "error" for d in result.diagnostics if d.code == "REF014")


def test_generated_profile_runs_myst_and_generated_checks_without_companion_profile():
    source = doc("source/jax_intro.md", "(jax_at_workaround)=\n#### A Workaround\n")
    generated = doc(
        "generated/jax_intro.md",
        "####变通方法\n\nSee {ref}`jax_at_workaround` and {eq}`missing-equation`.\n"
        "\n$$\n<!-- formula-not-decoded -->\n$$\n",
    )

    result = analyze_documents_architecture(
        (source, generated),
        profiles=("generated",),
        generated_pairs=(("source/jax_intro.md", "generated/jax_intro.md"),),
    )

    codes = {diagnostic.code for diagnostic in result.diagnostics}
    assert {"STR001", "REF002", "REF014", "GEN003", "GEN005"} <= codes
    assert any(d.severity.value == "error" for d in result.diagnostics if d.code == "GEN003")


def test_generated_profile_runs_algebra_checks():
    generated = doc("generated/bad.md", "$$\n(a+b)^2 = a^2 + b^2\n$$\n")

    result = analyze_documents_architecture((generated,), profiles=("generated",))

    by_code = {diagnostic.code: diagnostic for diagnostic in result.diagnostics}
    assert by_code["ALG001"].severity.value == "error"
    assert by_code["ALG001"].detail == "left - right = 2*a*b"


def test_generated_profile_accepts_valid_algebra_identity():
    generated = doc("generated/good.md", "$$\n(a+b)^2 = a^2 + 2*a*b + b^2\n$$\n")

    result = analyze_documents_architecture((generated,), profiles=("generated",))

    assert "ALG001" not in {diagnostic.code for diagnostic in result.diagnostics}


def test_architecture_algebra_engine_skips_spanless_math_facts():
    snapshot = FactSnapshot(
        display_math=(
            DisplayMathFact(
                fact_id="math-1",
                document_id="generated/bad.md",
                span=None,
                body="(a+b)^2 = a^2 + b^2",
                container="dollar-dollar",
            ),
        )
    )

    assert AlgebraEngine().run(QueryHost(snapshot)) == ()
