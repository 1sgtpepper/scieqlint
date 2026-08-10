from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from scieqlint import app as app_module
from scieqlint.api import check_documents, check_paths, graph_paths
from scieqlint.config.model import (
    AlgebraConfig,
    BaselineConfig,
    ChecksConfig,
    Config,
    ReferencesConfig,
    ScannerConfig,
)
from scieqlint.io import identity as identity_module
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.report.json import JsonReporter


def test_check_paths_rejects_missing_explicit_input(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="input not found"):
        check_paths([tmp_path / "missing.md"])


def test_graph_paths_rejects_missing_explicit_input(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="input not found"):
        graph_paths([tmp_path / "missing.md"])


def test_check_paths_returns_result_when_input_identity_is_unavailable(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "paper.md"
    path.write_text("# clean\n", encoding="utf-8")

    def deny_identity(_stat_result) -> object:
        raise PermissionError("identity detail must not escape")

    monkeypatch.setattr(identity_module.FileIdentity, "from_stat", deny_identity)

    result = check_paths([path])

    assert result.files_checked == 1
    assert result.diagnostics == ()


def test_check_paths_accepts_literal_file_with_glob_characters(tmp_path) -> None:
    path = tmp_path / "report[1].md"
    path.write_text("# clean\n", encoding="utf-8")

    result = check_paths([path])

    assert result.files_checked == 1


def test_check_paths_accepts_literal_directory_with_glob_characters(tmp_path) -> None:
    directory = tmp_path / "docs[old]"
    directory.mkdir()
    (directory / "paper.md").write_text("# clean\n", encoding="utf-8")

    result = check_paths([directory])

    assert result.files_checked == 1


def test_check_paths_expands_missing_glob_pattern(tmp_path) -> None:
    path = tmp_path / "report.md"
    path.write_text("# clean\n", encoding="utf-8")

    result = check_paths([str(tmp_path / "*.md")])

    assert result.files_checked == 1


@pytest.mark.public_regression
def test_check_paths_renders_absolute_input_relative_to_cwd(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    path = outside / "bad.md"
    path.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    monkeypatch.chdir(workspace)

    result = check_paths([path])

    diagnostic = result.diagnostics[0]
    assert diagnostic.span is not None
    assert diagnostic.span.path == PurePosixPath("../outside/bad.md")


def test_check_and_graph_paths_preserve_symlink_spelling_in_baseline(tmp_path, monkeypatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    target = tmp_path / "target.md"
    target.write_text(
        "$$\n(a+b)^2 = a^2 + b^2\n$$ {#energy}\n\nSee {eq}`energy`.\n",
        encoding="utf-8",
    )
    link = project / "link.md"
    link.symlink_to(target)
    monkeypatch.chdir(tmp_path)
    logical_path = link.relative_to(tmp_path)

    result = check_paths([logical_path])
    graph = graph_paths([logical_path])
    baseline = tmp_path / "baseline.json"
    config = tmp_path / "scieqlint.toml"
    baseline.write_text(JsonReporter().render(result), encoding="utf-8")
    config.write_text('[baseline]\nfiles = ["baseline.json"]\n', encoding="utf-8")

    baseline_result = check_paths([logical_path], config_path=config)

    diagnostic = baseline_result.diagnostics[0]
    assert diagnostic.suppressed is True
    assert diagnostic.span is not None
    assert diagnostic.span.path == PurePosixPath("project/link.md")
    assert {node.span.path for node in graph.nodes} == {PurePosixPath("project/link.md")}


def test_absolute_paths_keep_lexical_symlink_spelling(tmp_path, monkeypatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    target = tmp_path / "target.md"
    target.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")
    link = project / "link.md"
    link.symlink_to(target)
    monkeypatch.chdir(tmp_path)

    result = check_paths([link], absolute_paths=True)

    diagnostic = result.diagnostics[0]
    assert diagnostic.span is not None
    assert diagnostic.span.path == PurePosixPath(link.absolute().as_posix())


def test_read_error_uses_display_path_and_safe_os_error_detail(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    path = outside / "unreadable.md"
    path.write_text("# content\n", encoding="utf-8")
    monkeypatch.chdir(workspace)

    def fail_open(_path, *, encoding):
        raise PermissionError(13, "permission denied", str(path))

    monkeypatch.setattr(app_module, "open_text", fail_open)

    result = check_paths([path])

    diagnostic = result.diagnostics[0]
    assert diagnostic.code == "INP001"
    assert diagnostic.span is not None
    assert diagnostic.span.path == PurePosixPath("../outside/unreadable.md")
    assert diagnostic.message.endswith("../outside/unreadable.md")
    assert diagnostic.detail == "permission denied"
    assert str(tmp_path) not in diagnostic.message
    assert str(tmp_path) not in diagnostic.detail


def test_decode_error_detail_does_not_expose_the_input_path(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    path = outside / "invalid.md"
    path.write_bytes(b"\xff")
    monkeypatch.chdir(workspace)

    result = check_paths([path])

    diagnostic = result.diagnostics[0]
    assert diagnostic.code == "INP001"
    assert diagnostic.detail == "invalid start byte"
    assert str(tmp_path) not in diagnostic.message
    assert str(tmp_path) not in diagnostic.detail


def test_check_documents_runs_scanner_and_checks() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        DocumentKind.MARKDOWN,
    )
    result = check_documents([document], config=Config())
    assert result.files_checked == 1
    assert result.math_blocks_checked == 1
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["ALG001"]


def test_check_documents_honors_disabled_algebra_check() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        DocumentKind.MARKDOWN,
    )
    config = Config(checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)))
    result = check_documents([document], config=config)
    assert result.diagnostics == ()


def test_check_documents_honors_strict_missing_label_config() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\na = a\n$$\n",
        DocumentKind.MARKDOWN,
    )
    config = Config(checks=ChecksConfig(references=ReferencesConfig(missing_label_strict=True)))
    result = check_documents([document], config=config)
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF003"]


def test_strict_missing_label_check_keeps_fenced_math() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "```math\nx = x\n```\n",
        DocumentKind.MARKDOWN,
    )
    config = Config(checks=ChecksConfig(references=ReferencesConfig(missing_label_strict=True)))

    result = check_documents([document], config=config)

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF003"]


def test_strict_missing_label_check_ignores_inline_math() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "Text $x=x$.\n",
        DocumentKind.MARKDOWN,
    )
    config = Config(
        scanner=ScannerConfig(inline_math=True),
        checks=ChecksConfig(references=ReferencesConfig(missing_label_strict=True)),
    )

    result = check_documents([document], config=config)

    assert result.diagnostics == ()


def test_check_documents_marks_markdown_next_line_suppression() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "<!-- scieqlint-disable-next-line ALG001 -->\n$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert result.exit_code() == 0
    assert [(diagnostic.code, diagnostic.suppressed) for diagnostic in result.diagnostics] == [
        ("ALG001", True)
    ]


def test_check_documents_suppresses_adjacent_math_after_blank_body_line() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "<!-- scieqlint-disable-next-line ALG001 -->\n$$\n\n(a+b)^2 = a^2 + b^2\n$$\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert [(diagnostic.code, diagnostic.suppressed) for diagnostic in result.diagnostics] == [
        ("ALG001", True)
    ]


def test_check_documents_suppresses_adjacent_fenced_math_after_blank_body_line() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "<!-- scieqlint-disable-next-line ALG001 -->\n```math\n\n(a+b)^2 = a^2 + b^2\n```\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert [(diagnostic.code, diagnostic.suppressed) for diagnostic in result.diagnostics] == [
        ("ALG001", True)
    ]


def test_check_documents_keeps_next_line_suppression_on_the_adjacent_line() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "<!-- scieqlint-disable-next-line ALG001 -->\nordinary prose\n$$x=x+1$$\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert result.exit_code() == 1
    assert [(diagnostic.code, diagnostic.suppressed) for diagnostic in result.diagnostics] == [
        ("ALG001", False)
    ]


def test_check_documents_does_not_treat_inline_code_as_math_opener() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "<!-- scieqlint-disable-next-line ALG001 -->\n`$$`\n$$x=x+1$$\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert [(diagnostic.code, diagnostic.suppressed) for diagnostic in result.diagnostics] == [
        ("ALG001", False)
    ]


def test_disabled_markdown_math_does_not_break_suppression_collection() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "<!-- scieqlint-disable-next-line ALG001 -->\n$$\nx = x\n$$\n```math\ny = y\n```\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents(
        [document],
        config=Config(scanner=ScannerConfig(markdown=False, math_fences=False)),
    )

    assert result.diagnostics == ()


def test_check_documents_warns_for_unknown_suppression_code() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "<!-- scieqlint-disable-next-line NOPE999 -->\n$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert result.exit_code() == 1
    assert [(diagnostic.code, diagnostic.suppressed) for diagnostic in result.diagnostics] == [
        ("SUP001", False),
        ("ALG001", False),
    ]


def test_check_documents_does_not_suppress_different_code() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "<!-- scieqlint-disable-next-line REF002 -->\n$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        DocumentKind.MARKDOWN,
    )

    result = check_documents([document], config=Config())

    assert result.exit_code() == 1
    assert [(diagnostic.code, diagnostic.suppressed) for diagnostic in result.diagnostics] == [
        ("ALG001", False)
    ]


def test_check_documents_does_not_load_path_baselines() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        "$$\n(a+b)^2 = a^2 + b^2\n$$\n",
        DocumentKind.MARKDOWN,
    )
    config = Config(baseline=BaselineConfig(files=("missing-baseline.json",)))

    result = check_documents([document], config=config)

    assert result.exit_code() == 1
    assert result.diagnostics[0].suppressed is False
