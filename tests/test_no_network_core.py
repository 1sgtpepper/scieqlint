from __future__ import annotations

import builtins
import http.client
import os
import socket
import subprocess
import urllib.request
from pathlib import PurePosixPath
from typing import NoReturn

import pytest

from scieqlint.api import check_documents, check_paths
from scieqlint.config.model import Config, ScannerConfig
from scieqlint.io.source import DocumentKind, SourceDocument


class UnexpectedNetworkCallError(AssertionError):
    """Raised when deterministic analysis attempts to open a network connection."""


class UnexpectedDocumentSideEffectError(AssertionError):
    """Raised when analysis executes or imports document-provided code."""


def _deny_network(*_args: object, **_kwargs: object) -> NoReturn:
    raise UnexpectedNetworkCallError("analysis core attempted a network call")


def _deny_document_side_effect(*_args: object, **_kwargs: object) -> NoReturn:
    raise UnexpectedDocumentSideEffectError("analysis attempted to execute document code")


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trap standard-library network entry points reachable from analysis."""

    monkeypatch.setattr(socket, "create_connection", _deny_network)
    monkeypatch.setattr(socket, "getaddrinfo", _deny_network)
    monkeypatch.setattr(socket, "gethostbyname", _deny_network)
    monkeypatch.setattr(socket, "gethostbyname_ex", _deny_network)
    monkeypatch.setattr(socket.socket, "connect", _deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", _deny_network)
    monkeypatch.setattr(socket.socket, "send", _deny_network)
    monkeypatch.setattr(socket.socket, "sendall", _deny_network)
    monkeypatch.setattr(socket.socket, "sendto", _deny_network)
    monkeypatch.setattr(http.client.HTTPConnection, "connect", _deny_network)
    monkeypatch.setattr(http.client.HTTPSConnection, "connect", _deny_network)
    monkeypatch.setattr(urllib.request, "urlopen", _deny_network)


@pytest.fixture
def no_document_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trap execution, subprocess, and user-module import entry points."""

    monkeypatch.setattr(builtins, "eval", _deny_document_side_effect)
    monkeypatch.setattr(builtins, "exec", _deny_document_side_effect)
    monkeypatch.setattr(os, "system", _deny_document_side_effect)
    monkeypatch.setattr(subprocess, "run", _deny_document_side_effect)
    monkeypatch.setattr(subprocess, "Popen", _deny_document_side_effect)
    original_import = builtins.__import__

    def deny_user_module(
        name: str,
        module_globals: object = None,
        module_locals: object = None,
        fromlist: object = (),
        level: int = 0,
    ) -> object:
        if name == "user_project":
            raise UnexpectedDocumentSideEffectError(
                "analysis attempted to import a document-provided module"
            )
        return original_import(name, module_globals, module_locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", deny_user_module)


def _document(path: str, text: str, kind: DocumentKind) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, kind)


def test_public_analysis_path_does_not_fetch_hostile_external_targets(
    tmp_path,
    no_network: None,
) -> None:
    input_path = tmp_path / "generated.md"
    input_path.write_text(
        "\n".join(
            (
                "# Generated",
                "",
                "![equation](https://example.invalid/formula.svg)",
                "",
                "See [external equation](https://example.invalid/paper#eq-energy).",
                "",
                "Inline source: $E = mc^2$.",
            )
        ),
        encoding="utf-8",
    )

    result = check_paths(
        (input_path,),
        inline_math=True,
        absolute_paths=True,
    )

    assert result.files_checked == 1
    assert all(
        diagnostic.span is None
        or diagnostic.span.path == PurePosixPath(input_path.as_posix())
        for diagnostic in result.diagnostics
    )


def test_public_analysis_path_accepts_valid_input_without_document_side_effects(
    no_network: None,
    no_document_side_effects: None,
) -> None:
    document = _document(
        "safe.md",
        "\n".join(
            (
                "# Safe",
                "",
                "```{code-cell} python",
                "import user_project",
                "print('not run')",
                "```",
                "",
                "Inline math: $x = y$.",
            )
        ),
        DocumentKind.MARKDOWN,
    )

    result = check_documents(
        (document,),
        config=Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert result.files_checked == 1
    assert result.math_blocks_checked == 1


def test_public_analysis_path_remains_offline_for_malformed_notebook_boundary(
    no_network: None,
) -> None:
    notebook = _document(
        "generated.ipynb",
        "{",
        DocumentKind.NOTEBOOK,
    )

    result = check_documents((notebook,), config=Config())

    assert result.files_checked == 1
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["INP001"]
    assert result.diagnostics[0].detail == "Expecting property name enclosed in double quotes"


def test_public_analysis_path_reports_unreadable_input_without_continuing(
    tmp_path,
    no_network: None,
    no_document_side_effects: None,
) -> None:
    unreadable = tmp_path / "unreadable.md"
    unreadable.write_bytes(b"\xff")

    result = check_paths((unreadable,), absolute_paths=True)

    assert result.files_checked == 1
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["INP001"]
    assert result.diagnostics[0].span is not None
    assert result.diagnostics[0].span.path == PurePosixPath(unreadable.as_posix())


def test_no_network_guard_has_a_meaningful_negative_control(no_network: None) -> None:
    with pytest.raises(
        UnexpectedNetworkCallError,
        match="analysis core attempted a network call",
    ):
        socket.create_connection(("example.invalid", 443))


def test_no_document_side_effect_guard_has_a_meaningful_negative_control(
    no_document_side_effects: None,
) -> None:
    with pytest.raises(
        UnexpectedDocumentSideEffectError,
        match="analysis attempted to execute document code",
    ):
        builtins.exec("sentinel = True")

    with pytest.raises(
        UnexpectedDocumentSideEffectError,
        match="analysis attempted to import a document-provided module",
    ):
        builtins.__import__("user_project")
