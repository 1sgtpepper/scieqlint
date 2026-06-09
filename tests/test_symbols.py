from __future__ import annotations

import json
from pathlib import PurePosixPath

from click.testing import CliRunner

from scieqlint.api import check_documents
from scieqlint.cli import main
from scieqlint.config.model import ChecksConfig, Config, SymbolsConfig
from scieqlint.io.source import DocumentKind, SourceDocument


def test_symbol_check_reports_use_before_explicit_definition() -> None:
    result = check_documents(
        [
            _document(
                "paper.md",
                "$$\nE = m c^2\n$$\n\n"
                '<!-- scieqlint-symbol: E = energy, dim="M L^2 T^-2" -->\n'
                '<!-- scieqlint-symbol: m = mass, dim="M" -->\n'
                '<!-- scieqlint-symbol: c = speed, dim="L T^-1" -->\n',
            )
        ],
        config=_symbols_config(enabled=True),
    )

    assert [(diagnostic.code, diagnostic.detail) for diagnostic in result.diagnostics] == [
        ("SYM001", "E"),
        ("SYM001", "m"),
        ("SYM001", "c"),
    ]
    assert result.diagnostics[0].span is not None
    assert result.diagnostics[0].span.line == 2


def test_symbol_check_accepts_symbols_defined_before_use_across_ordered_files() -> None:
    result = check_documents(
        [
            _document("z-symbols.md", "<!-- scieqlint-symbol: E = energy -->\n"),
            _document("a-paper.md", "$$\nE = E\n$$\n"),
        ],
        config=_symbols_config(enabled=True),
    )

    assert result.diagnostics == ()


def test_symbol_check_is_disabled_by_default() -> None:
    result = check_documents(
        [_document("paper.md", "$$\nE = E\n$$\n")],
        config=Config(),
    )

    assert result.diagnostics == ()


def test_symbol_check_ignores_label_text_and_tex_operators() -> None:
    result = check_documents(
        [
            _document(
                "paper.md",
                "<!-- scieqlint-symbol: E = energy -->\n"
                "<!-- scieqlint-symbol: m = mass -->\n"
                "$$\n"
                "\\label{eq:energy}\n"
                "E = \\frac{m}{m}\n"
                "$$\n",
            )
        ],
        config=_symbols_config(enabled=True),
    )

    assert result.diagnostics == ()


def test_symbol_check_reports_multiline_symbol_columns() -> None:
    result = check_documents(
        [_document("paper.md", "$$\nA = B\nC = D\n$$\n")],
        config=_symbols_config(enabled=True),
    )

    spans = {
        diagnostic.detail: (diagnostic.span.line, diagnostic.span.col)
        for diagnostic in result.diagnostics
        if diagnostic.span is not None
    }
    assert spans == {
        "A": (2, 1),
        "B": (2, 5),
        "C": (3, 1),
        "D": (3, 5),
    }


def test_cli_json_exposes_undefined_symbol_diagnostic(tmp_path) -> None:
    doc = tmp_path / "paper.md"
    config = tmp_path / "scieqlint.toml"
    doc.write_text("$$\nE = m c^2\n$$\n", encoding="utf-8")
    config.write_text("[checks.symbols]\nenabled = true\n", encoding="utf-8")

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--config", str(config), "--format", "json"],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert [diagnostic["code"] for diagnostic in payload["diagnostics"]] == [
        "SYM001",
        "SYM001",
        "SYM001",
    ]
    assert payload["diagnostics"][0]["detail"] == "E"


def _document(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def _symbols_config(*, enabled: bool) -> Config:
    return Config(checks=ChecksConfig(symbols=SymbolsConfig(enabled=enabled)))
