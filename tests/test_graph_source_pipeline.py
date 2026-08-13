from __future__ import annotations

import errno
from pathlib import Path

import pytest

from scieqlint.api import check_paths, graph_paths


@pytest.mark.public_regression
def test_graph_paths_uses_project_root_order_ignore_and_display_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    book = tmp_path / "book"
    book.mkdir()
    _write_graph_document(book / "first.md", "first")
    _write_graph_document(book / "second.md", "second")
    _write_graph_document(book / "ignored.md", "ignored")
    config = tmp_path / "scieqlint.toml"
    config.write_text(
        "\n".join(
            (
                "[project]",
                'root = "book"',
                'order = ["second.md", "first.md", "*.md"]',
                "",
                "[ignore]",
                'files = ["ignored.md"]',
                "",
                "[baseline]",
                'files = ["missing-check-only-baseline.json"]',
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    from scieqlint import app

    opened: list[str] = []
    real_open_text = app.open_text

    def recording_open_text(path: Path, *, encoding: str):
        source_path = path if path.is_absolute() else tmp_path / path
        opened.append(source_path.resolve().relative_to(tmp_path.resolve()).as_posix())
        return real_open_text(path, encoding=encoding)

    monkeypatch.setattr(app, "open_text", recording_open_text)
    graph = graph_paths([], config_path=config)

    assert opened == ["book/second.md", "book/first.md"]
    assert [(node.kind, node.label) for node in graph.nodes] == [
        ("equation", "first"),
        ("reference", "first"),
        ("equation", "second"),
        ("reference", "second"),
    ]
    assert {node.span.path.as_posix() for node in graph.nodes} == {
        "book/first.md",
        "book/second.md",
    }


@pytest.mark.public_regression
def test_check_continues_but_graph_aborts_on_source_open_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    denied = tmp_path / "denied.md"
    denied.write_text("# denied\n", encoding="utf-8")
    readable = tmp_path / "readable.md"
    _write_graph_document(readable, "readable")

    from scieqlint import app

    real_open_text = app.open_text
    graph_documents_called = False

    def deny_source(path: Path, *, encoding: str):
        if path == denied:
            raise PermissionError(errno.EACCES, "denied", path)
        return real_open_text(path, encoding=encoding)

    def unexpected_graph_documents(*args, **kwargs):
        nonlocal graph_documents_called
        graph_documents_called = True
        raise AssertionError("graph construction must not observe a partial source set")

    monkeypatch.setattr(app, "open_text", deny_source)

    checked = check_paths([denied, readable])
    assert [(item.code, item.detail) for item in checked.diagnostics] == [("INP001", "denied")]
    assert checked.files_checked == 2
    assert checked.math_blocks_checked == 1

    monkeypatch.setattr(app, "graph_documents", unexpected_graph_documents)
    try:
        with pytest.raises(ValueError, match=r"INP001.*denied\.md.*denied") as caught:
            graph_paths([denied, readable])
    except PermissionError as error:
        pytest.fail(f"graph construction exposed a raw read failure: {error}")
    else:
        assert isinstance(caught.value.__cause__, PermissionError)

    assert not graph_documents_called


@pytest.mark.public_regression
def test_check_continues_but_graph_aborts_on_source_decode_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    denied = tmp_path / "denied.md"
    denied.write_bytes(b"\xff")
    readable = tmp_path / "readable.md"
    _write_graph_document(readable, "readable")

    checked = check_paths([denied, readable])
    assert [(item.code, item.detail) for item in checked.diagnostics] == [
        ("INP001", "invalid start byte")
    ]
    assert checked.files_checked == 2
    assert checked.math_blocks_checked == 1

    from scieqlint import app

    graph_documents_called = False

    def unexpected_graph_documents(*args, **kwargs):
        nonlocal graph_documents_called
        graph_documents_called = True
        raise AssertionError("graph construction must not observe a partial source set")

    monkeypatch.setattr(app, "graph_documents", unexpected_graph_documents)
    with pytest.raises(
        ValueError,
        match=r"INP001.*denied\.md.*invalid start byte",
    ) as caught:
        graph_paths([denied, readable])

    assert isinstance(caught.value.__cause__, UnicodeDecodeError)
    assert not graph_documents_called


def _write_graph_document(path: Path, label: str) -> None:
    path.write_text(
        f"$$\nx = x\n$$ {{#{label}}}\n\nSee {{eq}}`{label}`.\n",
        encoding="utf-8",
    )
