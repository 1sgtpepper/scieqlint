from pathlib import PurePosixPath

from scieqlint.compat.architecture_pipeline import analyze_documents_architecture
from scieqlint.engine.portability import PortabilityEngine
from scieqlint.engine.project import ProjectGraphEngine
from scieqlint.facts.project import ProjectMemberFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath("lecture.qmd"), text, DocumentKind.MARKDOWN)


def portability_diagnostics(text: str):
    snapshot = MySTFrontend().lower((doc(text),))
    return PortabilityEngine().run(QueryHost(snapshot))


def test_portability_engine_reports_math_without_alt_text():
    diagnostics = portability_diagnostics("Inline $x + y$.\n\n$$\nz = x + y\n$$\n")

    assert {"PORT001", "PORT002"}.issubset({diagnostic.code for diagnostic in diagnostics})


def test_quarto_renderings_crossref_option_is_flagged():
    diagnostics = portability_diagnostics(
        "```{python}\n"
        "#| label: fig-bad\n"
        "#| fig-cap: bad\n"
        "#| renderings: [light, dark]\n"
        "print(1)\n"
        "```\n"
    )

    assert "PORT004" in [diagnostic.code for diagnostic in diagnostics]


def test_quarto_crossref_label_requires_known_prefix():
    diagnostics = portability_diagnostics(
        "```{python}\n#| label: chart-growth\n#| fig-cap: Growth\nprint(1)\n```\n"
    )

    assert "PORT003" in [diagnostic.code for diagnostic in diagnostics]


def test_project_graph_engine_reports_duplicate_normalized_paths():
    snapshot = FactSnapshot(
        project_members=(
            project_member("chapters/intro.qmd", "chapters/intro.qmd"),
            project_member("./chapters/intro.qmd", "chapters/intro.qmd"),
        )
    )

    diagnostics = ProjectGraphEngine().run(QueryHost(snapshot))

    assert diagnostics[0].code == "PROJ002"
    assert diagnostics[0].detail == "chapters/intro.qmd"


def test_architecture_pipeline_runs_quarto_portability_profile():
    text = (
        "```{python}\n"
        "#| label: fig-bad\n"
        "#| fig-cap: bad\n"
        "#| renderings: [light, dark]\n"
        "print(1)\n"
        "```\n"
    )
    document = SourceDocument.from_text(PurePosixPath("plot.qmd"), text, DocumentKind.MARKDOWN)

    result = analyze_documents_architecture((document,), profiles=("quarto-project",))

    assert "PORT004" in [diagnostic.code for diagnostic in result.diagnostics]


def project_member(path: str, normalized_path: str) -> ProjectMemberFact:
    return ProjectMemberFact(
        fact_id=f"project::{path}",
        document_id=path,
        span=None,
        path=PurePosixPath(path),
        project_root=PurePosixPath("."),
        declared=True,
        discovered=True,
        normalized_path=PurePosixPath(normalized_path),
    )
