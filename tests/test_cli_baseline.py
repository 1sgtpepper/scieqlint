from __future__ import annotations

import json

from click.testing import CliRunner

from scieqlint.cli import main


def test_baseline_suppresses_known_diagnostic_in_json_output(tmp_path, monkeypatch) -> None:
    doc = tmp_path / "known.md"
    config = tmp_path / "scieqlint.toml"
    baseline = tmp_path / "scieqlint-baseline.json"
    doc.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    baseline.write_text(
        json.dumps(
            {
                "diagnostics": [
                    {
                        "code": "ALG001",
                        "path": "known.md",
                        "line": 2,
                        "col": 1,
                        "end_line": 2,
                        "end_col": 19,
                        "equation": "(a+b)^2 = a^2 + b^2",
                        "detail": "left - right = 2*a*b",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    config.write_text(
        '[baseline]\nfiles = ["scieqlint-baseline.json"]\n\n[report]\nshow_suppressed = true\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        main,
        ["check", "known.md", "--config", "scieqlint.toml", "--format", "json"],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["summary"]["errors"] == 0
    assert payload["diagnostics"][0]["suppressed"] is True
    assert payload["diagnostics"][0]["suppression_reason"] == "baseline"


def test_baseline_keeps_new_diagnostics_visible(tmp_path, monkeypatch) -> None:
    known = tmp_path / "known.md"
    new = tmp_path / "new.md"
    config = tmp_path / "scieqlint.toml"
    baseline = tmp_path / "scieqlint-baseline.json"
    known.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    new.write_text("$$\n(a-b)^2 = a^2 - b^2\n$$\n", encoding="utf-8")
    baseline.write_text(
        json.dumps(
            {
                "diagnostics": [
                    {
                        "code": "ALG001",
                        "path": "known.md",
                        "line": 2,
                        "col": 1,
                        "end_line": 2,
                        "end_col": 19,
                        "equation": "(a+b)^2 = a^2 + b^2",
                        "detail": "left - right = 2*a*b",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    config.write_text(
        '[baseline]\nfiles = ["scieqlint-baseline.json"]\n\n[report]\nshow_suppressed = true\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        main,
        ["check", "known.md", "new.md", "--config", "scieqlint.toml", "--format", "json"],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 1
    assert payload["summary"]["errors"] == 1
    assert [diagnostic["suppressed"] for diagnostic in payload["diagnostics"]] == [True, False]


def test_baseline_files_resolve_relative_to_project_root(tmp_path, monkeypatch) -> None:
    root = tmp_path / "book"
    root.mkdir()
    doc = root / "known.md"
    config = tmp_path / "scieqlint.toml"
    baseline = root / "scieqlint-baseline.json"
    doc.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    baseline.write_text(
        json.dumps(
            {
                "diagnostics": [
                    {
                        "code": "ALG001",
                        "path": "book/known.md",
                        "line": 2,
                        "col": 1,
                        "end_line": 2,
                        "end_col": 19,
                        "equation": "(a+b)^2 = a^2 + b^2",
                        "detail": "left - right = 2*a*b",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    config.write_text(
        '[project]\nroot = "book"\n\n[baseline]\n'
        'files = ["scieqlint-baseline.json"]\n\n'
        "[report]\nshow_suppressed = true\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        main,
        ["check", "book/known.md", "--config", "scieqlint.toml", "--format", "json"],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["diagnostics"][0]["suppressed"] is True


def test_invalid_baseline_file_reports_cli_error(tmp_path, monkeypatch) -> None:
    doc = tmp_path / "README.md"
    config = tmp_path / "scieqlint.toml"
    baseline = tmp_path / "bad-baseline.json"
    doc.write_text("# clean\n", encoding="utf-8")
    baseline.write_text(
        json.dumps({"diagnostics": [{"code": "ALG001", "line": True}]}),
        encoding="utf-8",
    )
    config.write_text('[baseline]\nfiles = ["bad-baseline.json"]\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["check", "README.md", "--config", "scieqlint.toml"])

    assert result.exit_code == 1
    assert "Error: baseline diagnostic line must be an integer or null" in result.output
