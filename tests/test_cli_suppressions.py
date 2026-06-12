from __future__ import annotations

import json

from click.testing import CliRunner

from scieqlint.cli import main


def test_json_output_hides_suppressed_diagnostics_by_default(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    doc.write_text(
        "<!-- scieqlint-disable-next-line ALG001 -->\n$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(doc), "--format", "json"])
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["diagnostics"] == []
    assert payload["summary"]["errors"] == 0


def test_json_output_includes_suppressed_diagnostics_when_configured(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    config = tmp_path / "scieqlint.toml"
    doc.write_text(
        "<!-- scieqlint-disable-next-line ALG001 -->\n$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        encoding="utf-8",
    )
    config.write_text("[report]\nshow_suppressed = true\n", encoding="utf-8")

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--format", "json", "--config", str(config)],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["diagnostics"][0]["code"] == "ALG001"
    assert payload["diagnostics"][0]["suppressed"] is True
    assert payload["diagnostics"][0]["suppression_reason"] == "source comment"
    assert payload["summary"]["errors"] == 0


def test_show_suppressed_config_includes_suppressed_text_output(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    config = tmp_path / "scieqlint.toml"
    doc.write_text(
        "<!-- scieqlint-disable-next-line ALG001 -->\n$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        encoding="utf-8",
    )
    config.write_text("[report]\nshow_suppressed = true\n", encoding="utf-8")

    result = CliRunner().invoke(main, ["check", str(doc), "--config", str(config)])

    assert result.exit_code == 0
    assert "suppressed error ALG001" in result.output


def test_markdown_suppression_hides_diagnostic_and_exits_zero(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    doc.write_text(
        "<!-- scieqlint-disable-next-line ALG001 -->\n$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(doc)])

    assert result.exit_code == 0
    assert "ALG001" not in result.output
    assert "found no diagnostics" in result.output


def test_markdown_suppression_inside_inline_code_does_not_suppress(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    doc.write_text(
        "`<!-- scieqlint-disable-next-line ALG001 -->`\n$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(doc)])

    assert result.exit_code == 1
    assert "ALG001" in result.output


def test_markdown_suppression_inside_code_fence_does_not_suppress(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    doc.write_text(
        "```md <!-- scieqlint-disable-next-line ALG001 -->\n```\n$$(a+b)^2 = a^2 + b^2$$\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(doc)])

    assert result.exit_code == 1
    assert "ALG001" in result.output


def test_notebook_markdown_suppression_hides_same_cell_diagnostic(tmp_path) -> None:
    doc = tmp_path / "notes.ipynb"
    doc.write_text(
        json.dumps(
            {
                "cells": [
                    _markdown_cell(
                        "<!-- scieqlint-disable-next-line ALG001 -->\n$$\n(a+b)^2 = a^2 + b^2\n$$\n"
                    )
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(doc)])

    assert result.exit_code == 0
    assert "ALG001" not in result.output
    assert "found no diagnostics" in result.output


def test_notebook_markdown_suppression_does_not_cross_cells(tmp_path) -> None:
    doc = tmp_path / "notes.ipynb"
    doc.write_text(
        json.dumps(
            {
                "cells": [
                    _markdown_cell(
                        "<!-- scieqlint-disable-next-line ALG001 -->\n$$\n(a+b)^2 = a^2 + b^2\n$$\n"
                    ),
                    _markdown_cell("$$\n(a+b)^2 = a^2 + b^2\n$$\n"),
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(doc), "--format", "json"])
    payload = json.loads(result.output)

    assert result.exit_code == 1
    assert [diagnostic["code"] for diagnostic in payload["diagnostics"]] == ["ALG001"]
    assert payload["diagnostics"][0]["cell"] == 1


def test_notebook_unknown_suppression_code_reports_cell_location(tmp_path) -> None:
    doc = tmp_path / "notes.ipynb"
    doc.write_text(
        json.dumps(
            {
                "cells": [_markdown_cell("<!-- scieqlint-disable-next-line NOPE999 -->\n")],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(doc), "--format", "json"])
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["diagnostics"][0]["code"] == "SUP001"
    assert payload["diagnostics"][0]["detail"] == "NOPE999"
    assert payload["diagnostics"][0]["cell"] == 0
    assert payload["diagnostics"][0]["cell_line"] == 1


def test_latex_current_block_suppression_hides_diagnostic_and_exits_zero(tmp_path) -> None:
    doc = tmp_path / "paper.tex"
    doc.write_text(
        "\\begin{equation}\n"
        "% scieqlint-disable-current-block ALG001\n"
        "(a+b)^2 = a^2 + b^2\n"
        "\\end{equation}\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(doc)])

    assert result.exit_code == 0
    assert "ALG001" not in result.output
    assert "found no diagnostics" in result.output


def test_unknown_suppression_code_reports_warning_and_does_not_suppress(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    doc.write_text(
        "<!-- scieqlint-disable-next-line NOPE999 -->\n$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(doc)])

    assert result.exit_code == 1
    assert "warning SUP001 unknown suppression code" in result.output
    assert "detail: NOPE999" in result.output
    assert "ALG001" in result.output


def test_malformed_suppression_code_reports_warning_and_does_not_suppress(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    doc.write_text(
        "<!-- scieqlint-disable-next-line 123 -->\n$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(doc)])

    assert result.exit_code == 1
    assert "warning SUP001 unknown suppression code" in result.output
    assert "detail: 123" in result.output
    assert "ALG001" in result.output


def test_empty_suppression_code_reports_warning_and_does_not_suppress(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    doc.write_text(
        "<!-- scieqlint-disable-next-line -->\n$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(doc)])

    assert result.exit_code == 1
    assert "warning SUP001 unknown suppression code" in result.output
    assert "detail: <empty>" in result.output
    assert "ALG001" in result.output


def test_latex_suppression_outside_block_does_not_suppress_later_block(tmp_path) -> None:
    doc = tmp_path / "paper.tex"
    doc.write_text(
        "% scieqlint-disable-current-block ALG001\n"
        "\\begin{equation}\n"
        "(a+b)^2 = a^2 + b^2\n"
        "\\end{equation}\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(doc)])

    assert result.exit_code == 1
    assert "ALG001" in result.output
    assert "found no diagnostics" not in result.output


def _markdown_cell(source: str) -> dict[str, object]:
    return {"cell_type": "markdown", "metadata": {}, "source": source}
