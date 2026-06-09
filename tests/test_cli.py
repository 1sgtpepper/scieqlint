from __future__ import annotations

import json

from click.testing import CliRunner

from scieqlint.cli import main
from scieqlint.config.load import load_config
from scieqlint.config.presets import read_preset_text


def test_help() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "scieqlint" in result.output.lower()


def test_check_help_lists_v010_flags() -> None:
    result = CliRunner().invoke(main, ["check", "--help"])
    assert result.exit_code == 0
    for option in ["--no-algebra", "--inline-math", "--strict-unknowns", "--absolute-paths"]:
        assert option in result.output
    assert "github" in result.output


def test_demo() -> None:
    result = CliRunner().invoke(main, ["demo"])
    assert result.exit_code == 0
    assert "ALG001" in result.output
    assert "REF002" in result.output


def test_check_clean_file_reports_empty_success(tmp_path) -> None:
    doc = tmp_path / "README.md"
    doc.write_text("# Example\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["check", str(doc)])
    assert result.exit_code == 0
    assert "found no diagnostics" in result.output
    assert "files checked: 1" in result.output


def test_check_quiet_suppresses_empty_success_text(tmp_path) -> None:
    doc = tmp_path / "README.md"
    doc.write_text("# Example\n", encoding="utf-8")

    result = CliRunner().invoke(main, ["check", str(doc), "--quiet"])

    assert result.exit_code == 0
    assert result.output == ""


def test_json_output_for_clean_file(tmp_path) -> None:
    doc = tmp_path / "README.md"
    doc.write_text("# Example\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["check", str(doc), "--format", "json"])
    assert result.exit_code == 0
    assert '"schema_version": "0.1"' in result.output


def test_check_writes_output_file(tmp_path) -> None:
    doc = tmp_path / "README.md"
    output = tmp_path / "result.json"
    doc.write_text("# Example\n", encoding="utf-8")

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--format", "json", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert result.output == ""
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["diagnostics"] == []
    assert payload["summary"]["errors"] == 0


def test_json_output_hides_suppressed_diagnostics_by_default(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    doc.write_text(
        "<!-- scieqlint-disable-next-line ALG001 -->\n"
        "$$\n"
        "(a+b)^2 = a^2 + b^2\n"
        "$$\n",
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
        "<!-- scieqlint-disable-next-line ALG001 -->\n"
        "$$\n"
        "(a+b)^2 = a^2 + b^2\n"
        "$$\n",
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
    assert payload["summary"]["errors"] == 1


def test_show_suppressed_config_does_not_change_text_output(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    config = tmp_path / "scieqlint.toml"
    doc.write_text(
        "<!-- scieqlint-disable-next-line ALG001 -->\n"
        "$$\n"
        "(a+b)^2 = a^2 + b^2\n"
        "$$\n",
        encoding="utf-8",
    )
    config.write_text("[report]\nshow_suppressed = true\n", encoding="utf-8")

    result = CliRunner().invoke(main, ["check", str(doc), "--config", str(config)])

    assert result.exit_code == 0
    assert "ALG001" not in result.output
    assert "found no diagnostics" in result.output


def test_graph_outputs_json_to_stdout() -> None:
    result = CliRunner().invoke(main, ["graph", "tests/fixtures/good/graph_refs.md"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "0.3"
    assert [node["kind"] for node in payload["nodes"]] == [
        "equation",
        "equation",
        "reference",
        "reference",
        "reference",
    ]
    assert {span["path"] for span in (node["span"] for node in payload["nodes"])} == {
        "tests/fixtures/good/graph_refs.md"
    }


def test_graph_writes_output_file(tmp_path) -> None:
    output = tmp_path / "graph.json"

    result = CliRunner().invoke(
        main,
        ["graph", "tests/fixtures/good/graph_refs.md", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert result.output == ""
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "0.3"
    assert len(payload["edges"]) == 3


def test_sarif_output_for_bad_equation(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    doc.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["check", str(doc), "--format", "sarif"])
    payload = json.loads(result.output)

    assert result.exit_code == 1
    assert payload["version"] == "2.1.0"
    assert payload["runs"][0]["results"][0]["ruleId"] == "ALG001"


def test_github_output_for_bad_equation(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    doc.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["check", str(doc), "--format", "github"])
    assert result.exit_code == 1
    assert result.output.startswith("::error title=ALG001 algebraic identity does not hold")
    assert f"file={doc.as_posix()},line=2,col=1" in result.output


def test_check_reports_bad_equation(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    doc.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["check", str(doc)])
    assert result.exit_code == 1
    assert "ALG001" in result.output
    assert "left - right = 2*a*b" in result.output


def test_markdown_suppression_hides_diagnostic_and_exits_zero(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    doc.write_text(
        "<!-- scieqlint-disable-next-line ALG001 -->\n"
        "$$\n"
        "(a+b)^2 = a^2 + b^2\n"
        "$$\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(doc)])

    assert result.exit_code == 0
    assert "ALG001" not in result.output
    assert "found no diagnostics" in result.output


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
        "<!-- scieqlint-disable-next-line NOPE999 -->\n"
        "$$\n"
        "(a+b)^2 = a^2 + b^2\n"
        "$$\n",
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
        "<!-- scieqlint-disable-next-line 123 -->\n"
        "$$\n"
        "(a+b)^2 = a^2 + b^2\n"
        "$$\n",
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
        "<!-- scieqlint-disable-next-line -->\n"
        "$$\n"
        "(a+b)^2 = a^2 + b^2\n"
        "$$\n",
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


def test_check_discovers_latex_source_files(tmp_path) -> None:
    doc = tmp_path / "paper.tex"
    doc.write_text("\\begin{equation}\n(a+b)^2 = a^2 + b^2\n\\end{equation}\n", encoding="utf-8")

    result = CliRunner().invoke(main, ["check", str(tmp_path)])

    assert result.exit_code == 1
    assert "ALG001" in result.output
    assert "paper.tex" in result.output


def test_check_discovers_notebook_source_files(tmp_path) -> None:
    doc = tmp_path / "notes.ipynb"
    doc.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": "$$\n(a+b)^2 = a^2 + b^2\n$$\n",
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(tmp_path)])

    assert result.exit_code == 1
    assert "ALG001" in result.output
    assert "notes.ipynb" in result.output


def test_no_algebra_suppresses_algebra_diagnostics(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    doc.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["check", str(doc), "--no-algebra"])
    assert result.exit_code == 0
    assert "ALG001" not in result.output


def test_no_algebra_preserves_unsupported_math_diagnostics(tmp_path) -> None:
    doc = tmp_path / "trig.md"
    doc.write_text("$$\n\\sin(x) = x\n$$\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["check", str(doc), "--no-algebra"])
    assert result.exit_code == 0
    assert "info PARSE021" in result.output


def test_check_reports_config_load_errors_as_click_errors(tmp_path) -> None:
    doc = tmp_path / "README.md"
    config = tmp_path / "missing.toml"
    doc.write_text("# Example\n", encoding="utf-8")

    result = CliRunner().invoke(main, ["check", str(doc), "--config", str(config)])

    assert result.exit_code == 1
    assert "Error: config not found" in result.output


def test_inline_math_is_opt_in(tmp_path) -> None:
    doc = tmp_path / "inline.md"
    doc.write_text("Bad inline math: $(a+b)^2 = a^2 + b^2$.\n", encoding="utf-8")
    default_result = CliRunner().invoke(main, ["check", str(doc)])
    inline_result = CliRunner().invoke(main, ["check", str(doc), "--inline-math"])
    assert default_result.exit_code == 0
    assert "ALG001" not in default_result.output
    assert inline_result.exit_code == 1
    assert "ALG001" in inline_result.output


def test_unsupported_function_reports_parse_diagnostic(tmp_path) -> None:
    doc = tmp_path / "trig.md"
    doc.write_text("$$\n\\sin(x) = x\n$$\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["check", str(doc)])
    assert result.exit_code == 0
    assert "info PARSE021" in result.output


def test_strict_unknowns_escalates_parse_diagnostic(tmp_path) -> None:
    doc = tmp_path / "trig.md"
    doc.write_text("$$\n\\sin(x) = x\n$$\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["check", str(doc), "--strict-unknowns"])
    assert result.exit_code == 1
    assert "error PARSE021" in result.output


def test_absolute_paths_render_resolved_diagnostic_path(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    doc.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["check", str(doc), "--absolute-paths"])
    assert result.exit_code == 1
    assert str(doc.resolve()) in result.output


def test_config_ignore_files_excludes_discovered_paths(tmp_path) -> None:
    kept = tmp_path / "kept.md"
    ignored = tmp_path / "ignored.md"
    config = tmp_path / "scieqlint.toml"
    kept.write_text("# Kept\n", encoding="utf-8")
    ignored.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    config.write_text(
        f'[ignore]\nfiles = ["{ignored.resolve().as_posix()}"]\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(tmp_path), "--config", str(config)])

    assert result.exit_code == 0
    assert "files checked: 1" in result.output


def test_config_ignore_files_does_not_exclude_explicit_file(tmp_path) -> None:
    doc = tmp_path / "ignored.md"
    config = tmp_path / "scieqlint.toml"
    doc.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    config.write_text(
        f'[ignore]\nfiles = ["{doc.resolve().as_posix()}"]\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(doc), "--config", str(config)])

    assert result.exit_code == 1
    assert "ALG001" in result.output


def test_project_order_controls_cross_file_symbol_checks_without_paths(tmp_path) -> None:
    root = tmp_path / "book"
    root.mkdir()
    symbols = root / "z-symbols.md"
    appendix = root / "m-appendix.md"
    paper = root / "a-paper.md"
    ignored = root / "ignored.md"
    config = tmp_path / "scieqlint.toml"
    symbols.write_text("<!-- scieqlint-symbol: E = energy -->\n", encoding="utf-8")
    appendix.write_text("# Appendix\n", encoding="utf-8")
    paper.write_text("$$\nE = E\n$$\n", encoding="utf-8")
    ignored.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    config.write_text(
        "\n".join(
            [
                "[project]",
                'root = "book"',
                'order = ["z-symbols.md", "a-paper.md"]',
                "",
                "[checks.symbols]",
                "enabled = true",
                "",
                "[ignore]",
                'files = ["ignored.md"]',
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        main,
        ["check", "--config", str(config), "--format", "json"],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["diagnostics"] == []
    assert payload["summary"]["files_checked"] == 3


def test_missing_reference_warning_does_not_fail(tmp_path) -> None:
    doc = tmp_path / "refs.md"
    doc.write_text("See {eq}`missing`.\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["check", str(doc)])
    assert result.exit_code == 0
    assert "warning REF002" in result.output


def test_init_writes_default_config(tmp_path) -> None:
    config = tmp_path / "scieqlint.toml"

    result = CliRunner().invoke(main, ["init", "--path", str(config)])

    assert result.exit_code == 0
    assert "wrote" in result.output
    assert "[checks.dimension]" in config.read_text(encoding="utf-8")


def test_presets_list_reports_packaged_presets() -> None:
    result = CliRunner().invoke(main, ["presets", "list"])

    assert result.exit_code == 0
    assert result.output == "mechanics\n"


def test_presets_show_reports_packaged_preset() -> None:
    result = CliRunner().invoke(main, ["presets", "show", "mechanics"])

    assert result.exit_code == 0
    assert result.output == read_preset_text("mechanics")


def test_presets_show_rejects_invalid_preset_name() -> None:
    result = CliRunner().invoke(main, ["presets", "show", "../mechanics"])

    assert result.exit_code == 1
    assert "unknown preset: ../mechanics" in result.output


def test_init_writes_packaged_preset_config(tmp_path) -> None:
    config = tmp_path / "mechanics.toml"

    result = CliRunner().invoke(main, ["init", "--path", str(config), "--preset", "mechanics"])

    assert result.exit_code == 0
    assert "wrote" in result.output
    assert config.read_text(encoding="utf-8") == read_preset_text("mechanics")
    loaded = load_config(config)
    assert loaded.checks.dimension.mode == "on"


def test_init_with_preset_rejects_unknown_preset_without_writing(tmp_path) -> None:
    config = tmp_path / "scieqlint.toml"

    result = CliRunner().invoke(main, ["init", "--path", str(config), "--preset", "unknown"])

    assert result.exit_code == 1
    assert "unknown preset: unknown" in result.output
    assert not config.exists()


def test_init_refuses_to_overwrite_existing_config(tmp_path) -> None:
    config = tmp_path / "scieqlint.toml"
    config.write_text("[scanner]\n", encoding="utf-8")

    result = CliRunner().invoke(main, ["init", "--path", str(config)])

    assert result.exit_code == 1
    assert "config already exists" in result.output


def test_init_with_preset_refuses_to_overwrite_existing_config(tmp_path) -> None:
    config = tmp_path / "scieqlint.toml"
    config.write_text("[scanner]\n", encoding="utf-8")

    result = CliRunner().invoke(main, ["init", "--path", str(config), "--preset", "mechanics"])

    assert result.exit_code == 1
    assert "config already exists" in result.output
    assert config.read_text(encoding="utf-8") == "[scanner]\n"


def test_explain_reports_known_diagnostic() -> None:
    result = CliRunner().invoke(main, ["explain", "alg001"])

    assert result.exit_code == 0
    assert "ALG001" in result.output


def test_explain_rejects_unknown_diagnostic() -> None:
    result = CliRunner().invoke(main, ["explain", "NOPE999"])

    assert result.exit_code == 1
    assert "unknown diagnostic code" in result.output
