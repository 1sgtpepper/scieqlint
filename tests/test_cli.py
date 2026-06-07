from __future__ import annotations

from click.testing import CliRunner

from scieqlint.cli import main


def test_help() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "scieqlint" in result.output.lower()


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


def test_json_output_for_clean_file(tmp_path) -> None:
    doc = tmp_path / "README.md"
    doc.write_text("# Example\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["check", str(doc), "--format", "json"])
    assert result.exit_code == 0
    assert '"schema_version": "0.1"' in result.output


def test_check_reports_bad_equation(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    doc.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["check", str(doc)])
    assert result.exit_code == 1
    assert "ALG001" in result.output
    assert "left - right = 2*a*b" in result.output


def test_missing_reference_warning_does_not_fail(tmp_path) -> None:
    doc = tmp_path / "refs.md"
    doc.write_text("See {eq}`missing`.\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["check", str(doc)])
    assert result.exit_code == 0
    assert "warning REF002" in result.output
