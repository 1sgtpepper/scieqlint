from __future__ import annotations

import json
import os
import stat

import pytest
from click.testing import CliRunner

from scieqlint import cli as cli_module
from scieqlint.cli import main
from scieqlint.config.load import load_config
from scieqlint.config.presets import read_preset_text
from scieqlint.io import identity as identity_module


def test_help() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "scieqlint" in result.output.lower()


def test_check_help_lists_v010_flags() -> None:
    result = CliRunner().invoke(main, ["check", "--help"])
    assert result.exit_code == 0
    for option in [
        "--no-algebra",
        "--inline-math",
        "--strict-unknowns",
        "--absolute-paths",
    ]:
        assert option in result.output
    assert "github" in result.output


def test_demo() -> None:
    result = CliRunner().invoke(main, ["demo"])
    assert result.exit_code == 0
    assert "ALG001" in result.output
    assert "    equation: (a+b)^2 = a^2 + b^2" in result.output
    assert "    detail: left - right = 2*a*b" in result.output
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


def test_check_refuses_to_overwrite_input(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    (tmp_path / "alias").mkdir()
    output = tmp_path / "alias" / ".." / "bad.md"
    original = "$$\n(a+b)^2 = a^2 + b^2\n$$\n"
    doc.write_text(original, encoding="utf-8")

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--format", "json", "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert doc.read_text(encoding="utf-8") == original


def test_check_refuses_replaced_exact_input_path(tmp_path, monkeypatch) -> None:
    doc = tmp_path / "source.md"
    original = "# consumed source\n"
    replacement = "# replacement\n"
    doc.write_text(original, encoding="utf-8")
    real_run = cli_module._run_check_paths

    def replace_source_after_run(*args, **kwargs):
        run = real_run(*args, **kwargs)
        doc.unlink()
        doc.write_text(replacement, encoding="utf-8")
        return run

    monkeypatch.setattr(cli_module, "_run_check_paths", replace_source_after_run)

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--format", "json", "--output", str(doc)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert doc.read_text(encoding="utf-8") == replacement


def test_check_refuses_replaced_ordinary_lexical_alias(tmp_path, monkeypatch) -> None:
    doc = tmp_path / "source.md"
    alias_directory = tmp_path / "alias"
    output = alias_directory / ".." / "source.md"
    replacement = "# replacement\n"
    alias_directory.mkdir()
    doc.write_text("# consumed source\n", encoding="utf-8")
    real_run = cli_module._run_check_paths

    def replace_source_after_run(*args, **kwargs):
        run = real_run(*args, **kwargs)
        doc.unlink()
        doc.write_text(replacement, encoding="utf-8")
        return run

    monkeypatch.setattr(cli_module, "_run_check_paths", replace_source_after_run)

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--format", "json", "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert doc.read_text(encoding="utf-8") == replacement


def test_check_refuses_deleted_input_through_symlinked_parent(tmp_path, monkeypatch) -> None:
    root = tmp_path / "root"
    root.mkdir()
    doc = root / "source.md"
    alias = tmp_path / "alias"
    output = alias / "source.md"
    alias.symlink_to(root, target_is_directory=True)
    doc.write_text("# consumed source\n", encoding="utf-8")
    real_run = cli_module._run_check_paths

    def remove_source_after_run(*args, **kwargs):
        run = real_run(*args, **kwargs)
        doc.unlink()
        return run

    monkeypatch.setattr(cli_module, "_run_check_paths", remove_source_after_run)

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--format", "json", "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert not doc.exists()
    assert not output.exists()


def test_check_refuses_symlink_to_replaced_source_role(tmp_path, monkeypatch) -> None:
    doc = tmp_path / "source.md"
    output = tmp_path / "result.json"
    replacement = "# replacement\n"
    doc.write_text("# consumed source\n", encoding="utf-8")
    output.symlink_to(doc)
    real_run = cli_module._run_check_paths

    def replace_source_after_run(*args, **kwargs):
        run = real_run(*args, **kwargs)
        doc.unlink()
        doc.write_text(replacement, encoding="utf-8")
        return run

    monkeypatch.setattr(cli_module, "_run_check_paths", replace_source_after_run)

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--format", "json", "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert doc.read_text(encoding="utf-8") == replacement
    assert output.is_symlink()


def test_check_refuses_hardlink_to_replacement_source_role(tmp_path, monkeypatch) -> None:
    doc = tmp_path / "source.md"
    output = tmp_path / "result.json"
    replacement = "# replacement\n"
    doc.write_text("# consumed source\n", encoding="utf-8")
    real_run = cli_module._run_check_paths

    def replace_source_and_create_output(*args, **kwargs):
        run = real_run(*args, **kwargs)
        doc.unlink()
        doc.write_text(replacement, encoding="utf-8")
        os.link(doc, output)
        return run

    monkeypatch.setattr(cli_module, "_run_check_paths", replace_source_and_create_output)

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--format", "json", "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert doc.read_text(encoding="utf-8") == replacement
    assert output.read_text(encoding="utf-8") == replacement


def test_check_allows_distinct_output_after_symlink_parent_input(tmp_path) -> None:
    root = tmp_path / "root"
    target_directory = root / "external" / "dir"
    target_directory.mkdir(parents=True)
    link = root / "link"
    link.symlink_to(target_directory, target_is_directory=True)
    consumed = root / "external" / "victim.md"
    output = root / "victim.md"
    original = "# physical target\n"
    consumed.write_text(original, encoding="utf-8")
    output.write_text("old output\n", encoding="utf-8")

    result = CliRunner().invoke(
        main,
        [
            "check",
            str(root / "link" / ".." / "victim.md"),
            "--format",
            "json",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["summary"]["files_checked"] == 1
    assert consumed.read_text(encoding="utf-8") == original


def test_graph_refuses_symlink_output_alias(tmp_path) -> None:
    doc = tmp_path / "graph.md"
    output = tmp_path / "graph.json"
    doc.write_text("$$\na = a\n$$ {#energy}\n", encoding="utf-8")
    output.symlink_to(doc)

    result = CliRunner().invoke(
        main,
        ["graph", str(doc), "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert doc.read_text(encoding="utf-8") == "$$\na = a\n$$ {#energy}\n"


def test_check_writes_distinct_output_symlink_target(tmp_path) -> None:
    doc = tmp_path / "README.md"
    target = tmp_path / "report-target.json"
    output = tmp_path / "report.json"
    doc.write_text("# clean\n", encoding="utf-8")
    target.write_text("placeholder\n", encoding="utf-8")
    output.symlink_to(target)

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--format", "json", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert output.is_symlink()
    assert json.loads(target.read_text(encoding="utf-8"))["diagnostics"] == []
    assert doc.read_text(encoding="utf-8") == "# clean\n"


def test_check_refuses_hardlink_output_alias(tmp_path) -> None:
    doc = tmp_path / "clean.md"
    output = tmp_path / "result.json"
    doc.write_text("# clean\n", encoding="utf-8")
    os.link(doc, output)

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert doc.read_text(encoding="utf-8") == "# clean\n"


def test_check_refuses_config_output_alias(tmp_path, monkeypatch) -> None:
    doc = tmp_path / "README.md"
    config = tmp_path / "scieqlint.toml"
    doc.write_text("# clean\n", encoding="utf-8")
    config.write_text("[report]\nshow_suppressed = true\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["check", "README.md", "--output", "scieqlint.toml"])

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert config.read_text(encoding="utf-8") == "[report]\nshow_suppressed = true\n"


def test_graph_refuses_config_output_alias(tmp_path, monkeypatch) -> None:
    doc = tmp_path / "README.md"
    config = tmp_path / "scieqlint.toml"
    doc.write_text("# clean\n", encoding="utf-8")
    config.write_text("[report]\nshow_suppressed = true\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        main,
        [
            "graph",
            "README.md",
            "--config",
            "scieqlint.toml",
            "--output",
            "scieqlint.toml",
        ],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert config.read_text(encoding="utf-8") == "[report]\nshow_suppressed = true\n"


def test_graph_refuses_hardlink_to_consumed_source_after_source_replacement(
    tmp_path,
    monkeypatch,
) -> None:
    doc = tmp_path / "source.md"
    output = tmp_path / "result.json"
    original = "$$\na = a\n$$ {#energy}\n"
    doc.write_text(original, encoding="utf-8")
    os.link(doc, output)
    real_run = cli_module._run_graph_paths

    def replace_source_after_run(*args, **kwargs):
        run = real_run(*args, **kwargs)
        doc.unlink()
        doc.write_text("# replacement\n", encoding="utf-8")
        return run

    monkeypatch.setattr(cli_module, "_run_graph_paths", replace_source_after_run)

    result = CliRunner().invoke(
        main,
        ["graph", str(doc), "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert output.read_text(encoding="utf-8") == original
    assert doc.read_text(encoding="utf-8") == "# replacement\n"


def test_graph_refuses_hardlink_to_replacement_source_role(tmp_path, monkeypatch) -> None:
    doc = tmp_path / "source.md"
    output = tmp_path / "result.json"
    original = "$$\na = a\n$$ {#energy}\n"
    replacement = "# replacement\n"
    doc.write_text(original, encoding="utf-8")
    real_run = cli_module._run_graph_paths

    def replace_source_and_create_output(*args, **kwargs):
        run = real_run(*args, **kwargs)
        doc.unlink()
        doc.write_text(replacement, encoding="utf-8")
        os.link(doc, output)
        return run

    monkeypatch.setattr(cli_module, "_run_graph_paths", replace_source_and_create_output)

    result = CliRunner().invoke(
        main,
        ["graph", str(doc), "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert doc.read_text(encoding="utf-8") == replacement
    assert output.read_text(encoding="utf-8") == replacement


def test_graph_refuses_hardlink_to_consumed_config_after_config_replacement(
    tmp_path,
    monkeypatch,
) -> None:
    doc = tmp_path / "README.md"
    config = tmp_path / "scieqlint.toml"
    output = tmp_path / "result.json"
    original = "[report]\nshow_suppressed = true\n"
    doc.write_text("$$\na = a\n$$ {#energy}\n", encoding="utf-8")
    config.write_text(original, encoding="utf-8")
    os.link(config, output)
    real_run = cli_module._run_graph_paths

    def replace_config_after_run(*args, **kwargs):
        run = real_run(*args, **kwargs)
        config.unlink()
        config.write_text("[report]\nshow_suppressed = false\n", encoding="utf-8")
        return run

    monkeypatch.setattr(cli_module, "_run_graph_paths", replace_config_after_run)

    result = CliRunner().invoke(
        main,
        ["graph", str(doc), "--config", str(config), "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert output.read_text(encoding="utf-8") == original


def test_graph_refuses_hardlink_to_replacement_config_role(tmp_path, monkeypatch) -> None:
    doc = tmp_path / "README.md"
    config = tmp_path / "scieqlint.toml"
    output = tmp_path / "result.json"
    original = "[report]\nshow_suppressed = true\n"
    replacement = "[report]\nshow_suppressed = false\n"
    doc.write_text("$$\na = a\n$$ {#energy}\n", encoding="utf-8")
    config.write_text(original, encoding="utf-8")
    real_run = cli_module._run_graph_paths

    def replace_config_and_create_output(*args, **kwargs):
        run = real_run(*args, **kwargs)
        config.unlink()
        config.write_text(replacement, encoding="utf-8")
        os.link(config, output)
        return run

    monkeypatch.setattr(cli_module, "_run_graph_paths", replace_config_and_create_output)

    result = CliRunner().invoke(
        main,
        ["graph", str(doc), "--config", str(config), "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert config.read_text(encoding="utf-8") == replacement
    assert output.read_text(encoding="utf-8") == replacement


def test_check_refuses_baseline_output_alias(tmp_path, monkeypatch) -> None:
    doc = tmp_path / "README.md"
    config = tmp_path / "scieqlint.toml"
    baseline = tmp_path / "baseline.json"
    doc.write_text("# clean\n", encoding="utf-8")
    baseline.write_text('{"diagnostics": []}\n', encoding="utf-8")
    config.write_text('[baseline]\nfiles = ["baseline.json"]\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        main,
        ["check", "README.md", "--config", "scieqlint.toml", "--output", "baseline.json"],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert baseline.read_text(encoding="utf-8") == '{"diagnostics": []}\n'


def test_check_refuses_when_input_identity_is_indeterminate(tmp_path, monkeypatch) -> None:
    doc = tmp_path / "clean.md"
    output = tmp_path / "result.json"
    doc.write_text("# clean\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def deny_identity(_stat_result) -> object:
        raise PermissionError("platform detail must not escape")

    monkeypatch.setattr(identity_module.FileIdentity, "from_stat", deny_identity)

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--format", "json", "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert "platform detail" not in result.output
    assert not output.exists()
    assert doc.read_text(encoding="utf-8") == "# clean\n"


def test_check_stdout_remains_available_when_input_identity_is_indeterminate(
    tmp_path,
    monkeypatch,
) -> None:
    doc = tmp_path / "clean.md"
    doc.write_text("# clean\n", encoding="utf-8")

    def deny_identity(_stat_result) -> object:
        raise PermissionError("platform detail must not escape")

    monkeypatch.setattr(identity_module.FileIdentity, "from_stat", deny_identity)

    result = CliRunner().invoke(main, ["check", str(doc)])

    assert result.exit_code == 0
    assert "found no diagnostics" in result.output
    assert "platform detail" not in result.output


def test_check_refuses_when_config_identity_is_indeterminate(tmp_path, monkeypatch) -> None:
    doc = tmp_path / "README.md"
    config = tmp_path / "scieqlint.toml"
    output = tmp_path / "result.json"
    doc.write_text("# clean\n", encoding="utf-8")
    config.write_text("[report]\nshow_suppressed = true\n", encoding="utf-8")
    original_from_stat = identity_module.FileIdentity.from_stat
    calls = 0

    def deny_config_identity(stat_result) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("config identity detail must not escape")
        return original_from_stat(stat_result)

    monkeypatch.setattr(identity_module.FileIdentity, "from_stat", deny_config_identity)

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--config", str(config), "--format", "json", "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert "config identity detail" not in result.output
    assert not output.exists()


def test_check_stdout_remains_available_when_config_identity_is_indeterminate(
    tmp_path,
    monkeypatch,
) -> None:
    doc = tmp_path / "README.md"
    config = tmp_path / "scieqlint.toml"
    doc.write_text("# clean\n", encoding="utf-8")
    config.write_text("[report]\nshow_suppressed = true\n", encoding="utf-8")
    original_from_stat = identity_module.FileIdentity.from_stat
    calls = 0

    def deny_config_identity(stat_result) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("config identity detail must not escape")
        return original_from_stat(stat_result)

    monkeypatch.setattr(identity_module.FileIdentity, "from_stat", deny_config_identity)

    result = CliRunner().invoke(main, ["check", str(doc), "--config", str(config)])

    assert result.exit_code == 0
    assert "found no diagnostics" in result.output
    assert "config identity detail" not in result.output


def test_check_refuses_when_baseline_identity_is_indeterminate(tmp_path, monkeypatch) -> None:
    doc = tmp_path / "README.md"
    config = tmp_path / "scieqlint.toml"
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "result.json"
    doc.write_text("# clean\n", encoding="utf-8")
    config.write_text('[baseline]\nfiles = ["baseline.json"]\n', encoding="utf-8")
    baseline.write_text('{"diagnostics": []}\n', encoding="utf-8")
    original_from_stat = identity_module.FileIdentity.from_stat
    calls = 0

    def deny_baseline_identity(stat_result) -> object:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise PermissionError("baseline identity detail must not escape")
        return original_from_stat(stat_result)

    monkeypatch.setattr(identity_module.FileIdentity, "from_stat", deny_baseline_identity)

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--config", str(config), "--format", "json", "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert "baseline identity detail" not in result.output
    assert not output.exists()


def test_check_stdout_remains_available_when_baseline_identity_is_indeterminate(
    tmp_path,
    monkeypatch,
) -> None:
    doc = tmp_path / "README.md"
    config = tmp_path / "scieqlint.toml"
    baseline = tmp_path / "baseline.json"
    doc.write_text("# clean\n", encoding="utf-8")
    config.write_text('[baseline]\nfiles = ["baseline.json"]\n', encoding="utf-8")
    baseline.write_text('{"diagnostics": []}\n', encoding="utf-8")
    original_from_stat = identity_module.FileIdentity.from_stat
    calls = 0

    def deny_baseline_identity(stat_result) -> object:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise PermissionError("baseline identity detail must not escape")
        return original_from_stat(stat_result)

    monkeypatch.setattr(identity_module.FileIdentity, "from_stat", deny_baseline_identity)

    result = CliRunner().invoke(main, ["check", str(doc), "--config", str(config)])

    assert result.exit_code == 0
    assert "found no diagnostics" in result.output
    assert "baseline identity detail" not in result.output


def test_graph_refuses_when_source_identity_is_indeterminate(tmp_path, monkeypatch) -> None:
    doc = tmp_path / "graph.md"
    output = tmp_path / "result.json"
    doc.write_text("$$\na = a\n$$ {#energy}\n", encoding="utf-8")

    def deny_identity(_stat_result) -> object:
        raise PermissionError("graph identity detail must not escape")

    monkeypatch.setattr(identity_module.FileIdentity, "from_stat", deny_identity)

    result = CliRunner().invoke(main, ["graph", str(doc), "--output", str(output)])

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert "graph identity detail" not in result.output
    assert not output.exists()


def test_graph_refuses_when_config_identity_is_indeterminate(tmp_path, monkeypatch) -> None:
    doc = tmp_path / "graph.md"
    config = tmp_path / "scieqlint.toml"
    output = tmp_path / "result.json"
    doc.write_text("$$\na = a\n$$ {#energy}\n", encoding="utf-8")
    config.write_text("[report]\nshow_suppressed = true\n", encoding="utf-8")
    original_from_stat = identity_module.FileIdentity.from_stat
    calls = 0

    def deny_config_identity(stat_result) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("graph config identity detail must not escape")
        return original_from_stat(stat_result)

    monkeypatch.setattr(identity_module.FileIdentity, "from_stat", deny_config_identity)

    result = CliRunner().invoke(
        main,
        ["graph", str(doc), "--config", str(config), "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert "graph config identity detail" not in result.output
    assert not output.exists()


def test_graph_stdout_remains_available_when_source_identity_is_indeterminate(
    tmp_path,
    monkeypatch,
) -> None:
    doc = tmp_path / "graph.md"
    doc.write_text("$$\na = a\n$$ {#energy}\n", encoding="utf-8")

    def deny_identity(_stat_result) -> object:
        raise PermissionError("graph identity detail must not escape")

    monkeypatch.setattr(identity_module.FileIdentity, "from_stat", deny_identity)

    result = CliRunner().invoke(main, ["graph", str(doc)])

    assert result.exit_code == 0
    assert '"schema_version": "0.3"' in result.output
    assert "graph identity detail" not in result.output


def test_graph_stdout_remains_available_when_config_identity_is_indeterminate(
    tmp_path,
    monkeypatch,
) -> None:
    doc = tmp_path / "graph.md"
    config = tmp_path / "scieqlint.toml"
    doc.write_text("$$\na = a\n$$ {#energy}\n", encoding="utf-8")
    config.write_text("[report]\nshow_suppressed = true\n", encoding="utf-8")
    original_from_stat = identity_module.FileIdentity.from_stat
    calls = 0

    def deny_config_identity(stat_result) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("graph config identity detail must not escape")
        return original_from_stat(stat_result)

    monkeypatch.setattr(identity_module.FileIdentity, "from_stat", deny_config_identity)

    result = CliRunner().invoke(main, ["graph", str(doc), "--config", str(config)])

    assert result.exit_code == 0
    assert '"schema_version": "0.3"' in result.output
    assert "graph config identity detail" not in result.output


def test_check_refuses_output_swapped_to_input_before_open(tmp_path, monkeypatch) -> None:
    doc = tmp_path / "bad.md"
    output = tmp_path / "result.json"
    original = "ORIGINAL\n"
    doc.write_text(original, encoding="utf-8")
    output.write_text("placeholder\n", encoding="utf-8")
    checked = False
    real_open = cli_module.os.open

    def swap_before_open(path, flags, mode=0o777):
        nonlocal checked
        if path == output and not checked:
            output.unlink()
            output.symlink_to(doc)
            checked = True
        return real_open(path, flags, mode)

    monkeypatch.setattr(cli_module.os, "open", swap_before_open)

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--format", "json", "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert doc.read_text(encoding="utf-8") == original


def test_check_refuses_existing_output_when_output_identity_is_unavailable(
    tmp_path,
    monkeypatch,
) -> None:
    doc = tmp_path / "clean.md"
    output = tmp_path / "result.json"
    original = "placeholder\n"
    doc.write_text("# clean\n", encoding="utf-8")
    output.write_text(original, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    real_fstat = cli_module.os.fstat
    calls = 0

    def deny_output_identity(descriptor: int):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError("output identity detail must not escape")
        return real_fstat(descriptor)

    monkeypatch.setattr(cli_module.os, "fstat", deny_output_identity)

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--format", "json", "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert "output identity detail" not in result.output
    assert output.read_text(encoding="utf-8") == original


def test_check_refuses_hardlink_to_consumed_source_after_source_replacement(
    tmp_path,
    monkeypatch,
) -> None:
    doc = tmp_path / "source.md"
    output = tmp_path / "result.json"
    original = "# consumed source\n"
    doc.write_text(original, encoding="utf-8")
    os.link(doc, output)
    real_run = cli_module._run_check_paths

    def replace_source_after_run(*args, **kwargs):
        run = real_run(*args, **kwargs)
        doc.unlink()
        doc.write_text("# replacement\n", encoding="utf-8")
        return run

    monkeypatch.setattr(cli_module, "_run_check_paths", replace_source_after_run)

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--format", "json", "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert output.read_text(encoding="utf-8") == original
    assert doc.read_text(encoding="utf-8") == "# replacement\n"


def test_check_writes_distinct_output_when_consumed_path_disappears(
    tmp_path,
    monkeypatch,
) -> None:
    doc = tmp_path / "source.md"
    output = tmp_path / "result.json"
    doc.write_text("# consumed source\n", encoding="utf-8")
    real_run = cli_module._run_check_paths

    def remove_source_after_run(*args, **kwargs):
        run = real_run(*args, **kwargs)
        doc.unlink()
        return run

    monkeypatch.setattr(cli_module, "_run_check_paths", remove_source_after_run)

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--format", "json", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["diagnostics"] == []
    assert not doc.exists()


def test_check_refuses_hardlink_to_consumed_config_after_config_replacement(
    tmp_path,
    monkeypatch,
) -> None:
    doc = tmp_path / "README.md"
    config = tmp_path / "scieqlint.toml"
    output = tmp_path / "result.json"
    original = "[report]\nshow_suppressed = true\n"
    doc.write_text("# clean\n", encoding="utf-8")
    config.write_text(original, encoding="utf-8")
    os.link(config, output)
    real_run = cli_module._run_check_paths

    def replace_config_after_run(*args, **kwargs):
        run = real_run(*args, **kwargs)
        config.unlink()
        config.write_text("[report]\nshow_suppressed = false\n", encoding="utf-8")
        return run

    monkeypatch.setattr(cli_module, "_run_check_paths", replace_config_after_run)

    result = CliRunner().invoke(
        main,
        [
            "check",
            str(doc),
            "--config",
            str(config),
            "--format",
            "json",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert output.read_text(encoding="utf-8") == original


def test_check_refuses_hardlink_to_consumed_baseline_after_baseline_replacement(
    tmp_path,
    monkeypatch,
) -> None:
    doc = tmp_path / "README.md"
    config = tmp_path / "scieqlint.toml"
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "result.json"
    original = '{"diagnostics": []}\n'
    doc.write_text("# clean\n", encoding="utf-8")
    baseline.write_text(original, encoding="utf-8")
    config.write_text('[baseline]\nfiles = ["baseline.json"]\n', encoding="utf-8")
    os.link(baseline, output)
    real_run = cli_module._run_check_paths

    def replace_baseline_after_run(*args, **kwargs):
        run = real_run(*args, **kwargs)
        baseline.unlink()
        baseline.write_text(original, encoding="utf-8")
        return run

    monkeypatch.setattr(cli_module, "_run_check_paths", replace_baseline_after_run)

    result = CliRunner().invoke(
        main,
        [
            "check",
            str(doc),
            "--config",
            str(config),
            "--format",
            "json",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert output.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("role", ["config", "baseline"])
def test_check_refuses_symlink_to_replaced_consumed_role(tmp_path, monkeypatch, role) -> None:
    doc = tmp_path / "README.md"
    config = tmp_path / "scieqlint.toml"
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "result.json"
    doc.write_text("# clean\n", encoding="utf-8")
    config.write_text(
        '[baseline]\nfiles = ["baseline.json"]\n' if role == "baseline" else "",
        encoding="utf-8",
    )
    baseline.write_text('{"diagnostics": []}\n', encoding="utf-8")
    consumed_role = baseline if role == "baseline" else config
    output.symlink_to(consumed_role)
    real_run = cli_module._run_check_paths

    def replace_role_after_run(*args, **kwargs):
        run = real_run(*args, **kwargs)
        consumed_role.unlink()
        consumed_role.write_text(
            '{"diagnostics": []}\n' if role == "baseline" else "[report]\n",
            encoding="utf-8",
        )
        return run

    monkeypatch.setattr(cli_module, "_run_check_paths", replace_role_after_run)

    arguments = [
        "check",
        "--config",
        str(config),
        str(doc),
        "--format",
        "json",
        "--output",
        str(output),
    ]
    result = CliRunner().invoke(main, arguments)

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert output.is_symlink()


def test_check_refuses_hardlink_to_replacement_baseline_role(tmp_path, monkeypatch) -> None:
    doc = tmp_path / "README.md"
    config = tmp_path / "scieqlint.toml"
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "result.json"
    original = '{"diagnostics": []}\n'
    replacement = '{"diagnostics": [{"code": "ALG001"}]}\n'
    doc.write_text("# clean\n", encoding="utf-8")
    baseline.write_text(original, encoding="utf-8")
    config.write_text('[baseline]\nfiles = ["baseline.json"]\n', encoding="utf-8")
    real_run = cli_module._run_check_paths

    def replace_baseline_and_create_output(*args, **kwargs):
        run = real_run(*args, **kwargs)
        baseline.unlink()
        baseline.write_text(replacement, encoding="utf-8")
        os.link(baseline, output)
        return run

    monkeypatch.setattr(cli_module, "_run_check_paths", replace_baseline_and_create_output)

    result = CliRunner().invoke(
        main,
        [
            "check",
            str(doc),
            "--config",
            str(config),
            "--format",
            "json",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert baseline.read_text(encoding="utf-8") == replacement
    assert output.read_text(encoding="utf-8") == replacement


def test_check_refuses_dangling_output_symlink_without_recreating_target(
    tmp_path,
    monkeypatch,
) -> None:
    doc = tmp_path / "source.md"
    output = tmp_path / "result.json"
    doc.write_text("# consumed source\n", encoding="utf-8")
    output.write_text("placeholder\n", encoding="utf-8")
    real_open = cli_module.os.open
    swapped = False

    def create_dangling_alias(path, flags, mode=0o777):
        nonlocal swapped
        if path == output and flags & os.O_EXCL and not swapped:
            output.unlink()
            output.symlink_to(doc)
            doc.unlink()
            swapped = True
        return real_open(path, flags, mode)

    monkeypatch.setattr(cli_module.os, "open", create_dangling_alias)

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--format", "json", "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "refusing to overwrite analysis input" in result.output
    assert not doc.exists()
    assert output.is_symlink()


@pytest.mark.skipif(os.name == "nt", reason="POSIX file permissions are required")
def test_check_writes_existing_owner_write_only_output(tmp_path) -> None:
    doc = tmp_path / "README.md"
    output = tmp_path / "result.json"
    doc.write_text("# clean\n", encoding="utf-8")
    output.write_text("old\n", encoding="utf-8")
    output.chmod(stat.S_IWUSR)

    try:
        result = CliRunner().invoke(
            main,
            ["check", str(doc), "--format", "json", "--output", str(output)],
        )
    finally:
        output.chmod(stat.S_IRUSR | stat.S_IWUSR)

    assert result.exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["diagnostics"] == []


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


def test_graph_rejects_missing_explicit_input(tmp_path) -> None:
    result = CliRunner().invoke(main, ["graph", str(tmp_path / "missing.md")])

    assert result.exit_code == 2
    assert "Error: input not found" in result.output


def test_check_accepts_literal_path_with_glob_characters(tmp_path) -> None:
    path = tmp_path / "report[1].md"
    path.write_text("# clean\n", encoding="utf-8")

    result = CliRunner().invoke(main, ["check", str(path)])

    assert result.exit_code == 0
    assert "files checked: 1" in result.output


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
        "<!-- scieqlint-disable-next-line ALG001 -->\n$$\n(a+b)^2 = a^2 + b^2\n$$\n",
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


def test_check_discovers_latex_source_files(tmp_path) -> None:
    doc = tmp_path / "paper.tex"
    doc.write_text(
        "\\begin{equation}\n(a+b)^2 = a^2 + b^2\n\\end{equation}\n",
        encoding="utf-8",
    )

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


def test_check_reports_oversized_notebook_integer_as_input_diagnostic(tmp_path) -> None:
    doc = tmp_path / "huge.ipynb"
    doc.write_text(
        '{"cells":[],"metadata":{},"nbformat":' + "9" * 5000 + ',"nbformat_minor":0}',
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(doc), "--format", "json"])
    payload = json.loads(result.output)

    assert result.exit_code == 1
    assert [diagnostic["code"] for diagnostic in payload["diagnostics"]] == ["INP001"]
    assert payload["diagnostics"][0]["detail"] == "JSON integer exceeds 4096 digits"
    assert "Traceback" not in result.output


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


def test_check_reports_config_load_errors_as_operational_errors(tmp_path) -> None:
    doc = tmp_path / "README.md"
    config = tmp_path / "missing.toml"
    doc.write_text("# Example\n", encoding="utf-8")

    result = CliRunner().invoke(main, ["check", str(doc), "--config", str(config)])

    assert result.exit_code == 2
    assert "Error: config not found" in result.output


def test_check_rejects_unknown_config_before_analysis(tmp_path) -> None:
    doc = tmp_path / "bad.md"
    config = tmp_path / "scieqlint.toml"
    doc.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    config.write_text("[checks.algebr]\nenabled = false\n", encoding="utf-8")

    result = CliRunner().invoke(main, ["check", str(doc), "--config", str(config)])

    assert result.exit_code == 2
    assert "Error: unknown config key" in result.output
    assert "ALG001" not in result.output


def test_check_rejects_missing_explicit_input(tmp_path) -> None:
    result = CliRunner().invoke(main, ["check", str(tmp_path / "missing.md")])

    assert result.exit_code == 2
    assert "Error: input not found" in result.output


def test_check_reports_invalid_utf8_and_continues(tmp_path) -> None:
    invalid = tmp_path / "invalid.md"
    valid = tmp_path / "valid.md"
    invalid.write_bytes(b"\xff\n")
    valid.write_text("# Valid\n", encoding="utf-8")

    result = CliRunner().invoke(
        main,
        ["check", str(invalid), str(valid), "--format", "json"],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 1
    assert "INP001" in result.output
    assert payload["summary"]["files_checked"] == 2


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


def test_configured_strict_unknowns_escalates_parse_diagnostic(tmp_path) -> None:
    doc = tmp_path / "trig.md"
    doc.write_text("$$\n\\sin(x) = x\n$$\n", encoding="utf-8")
    config = tmp_path / "scieqlint.toml"
    config.write_text("[parser]\nstrict_unknowns = true\n", encoding="utf-8")

    result = CliRunner().invoke(main, ["check", str(doc), "--config", str(config)])

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
    assert payload["summary"]["files_checked"] == 2


def test_empty_project_order_preserves_no_path_current_directory_behavior(
    tmp_path,
    monkeypatch,
) -> None:
    book = tmp_path / "book"
    chapter = book / "chapter"
    chapter.mkdir(parents=True)
    (book / "scieqlint.toml").write_text('[project]\nroot = "."\norder = []\n', encoding="utf-8")
    (book / "outside.md").write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    (chapter / "inside.md").write_text("# clean\n", encoding="utf-8")
    monkeypatch.chdir(chapter)

    result = CliRunner().invoke(main, ["check", "--format", "json"])
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["summary"]["files_checked"] == 1
    assert payload["diagnostics"] == []


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

    assert result.exit_code == 2
    assert "Error: baseline diagnostic line must be an integer or null" in result.output


def test_check_reports_output_failures_as_operational_errors(tmp_path) -> None:
    doc = tmp_path / "README.md"
    output = tmp_path / "output-directory"
    doc.write_text("# clean\n", encoding="utf-8")
    output.mkdir()

    result = CliRunner().invoke(main, ["check", str(doc), "--output", str(output)])

    assert result.exit_code == 2
    assert "Error:" in result.output


def test_project_absolute_root_controls_default_paths(tmp_path) -> None:
    root = tmp_path / "book"
    root.mkdir()
    doc = root / "paper.md"
    config = tmp_path / "scieqlint.toml"
    doc.write_text("# Paper\n", encoding="utf-8")
    config.write_text(
        f'[project]\nroot = "{root.resolve().as_posix()}"\norder = ["paper.md"]\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", "--config", str(config)])

    assert result.exit_code == 0
    assert "files checked: 1" in result.output


def test_project_ignore_can_match_absolute_discovered_paths_outside_root(tmp_path) -> None:
    root = tmp_path / "book"
    external = tmp_path / "external"
    root.mkdir()
    external.mkdir()
    ignored = external / "ignored.md"
    config = tmp_path / "scieqlint.toml"
    ignored.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    config.write_text(
        "\n".join(
            [
                "[project]",
                'root = "book"',
                "",
                "[ignore]",
                f'files = ["{ignored.resolve().as_posix()}"]',
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["check", str(external), "--config", str(config)])

    assert result.exit_code == 0
    assert "files checked: 0" in result.output


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
    load_config(config)


def test_presets_list_reports_packaged_presets() -> None:
    result = CliRunner().invoke(main, ["presets", "list"])

    assert result.exit_code == 0
    assert result.output == "generated-myst\nmechanics\n"


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


def test_init_writes_generated_myst_preset_config(tmp_path) -> None:
    config = tmp_path / "generated-myst.toml"

    result = CliRunner().invoke(main, ["init", "--path", str(config), "--preset", "generated-myst"])

    assert result.exit_code == 0
    assert "wrote" in result.output
    assert config.read_text(encoding="utf-8") == read_preset_text("generated-myst")
    loaded = load_config(config)
    assert loaded.scanner.inline_math is True
    assert loaded.parser.strict_unknowns is True


def test_generated_myst_preset_emits_github_annotations(tmp_path) -> None:
    doc = tmp_path / "generated.md"
    doc.write_text(
        "\n".join(
            [
                "# Generated",
                "",
                "Inline generated math can drift: $\\sin(x) = x$.",
                "",
                "See {eq}`missing`.",
            ]
        ),
        encoding="utf-8",
    )
    config = tmp_path / "generated-myst.toml"
    config.write_text(read_preset_text("generated-myst"), encoding="utf-8")

    result = CliRunner().invoke(
        main,
        ["check", str(doc), "--config", str(config), "--format", "github"],
    )

    assert result.exit_code == 1
    assert "::error title=PARSE021" in result.output
    assert "::warning title=REF002" in result.output


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


def test_init_reports_output_failures_as_operational_errors(tmp_path) -> None:
    config = tmp_path / "missing" / "scieqlint.toml"

    result = CliRunner().invoke(main, ["init", "--path", str(config)])

    assert result.exit_code == 2
    assert "Error:" in result.output
    assert "Traceback" not in result.output


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
