from pathlib import PurePosixPath

from scieqlint.compat.architecture_pipeline import analyze_documents_architecture
from scieqlint.io.source import DocumentKind, SourceDocument


def test_quarto_renderings_crossref_option_is_flagged():
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
