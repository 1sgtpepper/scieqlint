from __future__ import annotations

from collections.abc import Callable
from pathlib import Path, PurePosixPath

import pytest
from click.testing import CliRunner

from scieqlint.api import check_documents, check_paths, graph_documents, graph_paths
from scieqlint.cli import main
from scieqlint.config.model import Config
from scieqlint.io.source import DocumentKind, SourceDocument


@pytest.mark.parametrize("command", ["check", "graph"])
@pytest.mark.public_regression
def test_cli_rejects_explicit_unsupported_files_without_scanning_markdown(
    tmp_path: Path,
    command: str,
) -> None:
    path = tmp_path / "unsupported.txt"
    path.write_text("$$\n(a+b)^2 = a^2 + b^2\n$$\n", encoding="utf-8")

    result = CliRunner().invoke(main, [command, str(path)])

    assert result.exit_code == 2
    assert "unsupported source kind '.txt'" in result.output
    assert "ALG001" not in result.output


@pytest.mark.parametrize("operation", [check_paths, graph_paths])
def test_path_api_rejects_explicit_unsupported_files(
    tmp_path: Path,
    operation: Callable[..., object],
) -> None:
    path = tmp_path / "unsupported"
    path.write_text("# prose\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"unsupported source kind '<none>'"):
        operation([path])


@pytest.mark.parametrize("operation", [check_documents, graph_documents])
def test_document_api_rejects_unknown_document_kind(
    operation: Callable[..., object],
) -> None:
    document = SourceDocument.from_text(
        PurePosixPath("memory.input"),
        "# prose\n",
        DocumentKind.UNKNOWN,
    )

    with pytest.raises(ValueError, match=r"unsupported source kind '.input'"):
        operation([document], config=Config())


def test_directory_discovery_still_filters_unsupported_files(tmp_path: Path) -> None:
    (tmp_path / "kept.MD").write_text(
        "$$\nx = x\n$$ {#kept}\n",
        encoding="utf-8",
    )
    (tmp_path / "ignored.txt").write_text("$$\nx=x+1\n$$\n", encoding="utf-8")

    checked = check_paths([tmp_path])
    graph = graph_paths([tmp_path])

    assert checked.files_checked == 1
    assert all(
        item.span is None or item.span.path.name != "ignored.txt" for item in checked.diagnostics
    )
    assert [(node.kind, node.label) for node in graph.nodes] == [("equation", "kept")]
