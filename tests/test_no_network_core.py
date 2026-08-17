from __future__ import annotations

import http.client
import socket
import urllib.request
from pathlib import PurePosixPath
from typing import NoReturn

import pytest

from scieqlint.api import check_documents
from scieqlint.config.model import Config, ScannerConfig
from scieqlint.io.source import DocumentKind, SourceDocument


class UnexpectedNetworkCallError(AssertionError):
    """Raised when deterministic analysis attempts to open a network connection."""


def _deny_network(*_args: object, **_kwargs: object) -> NoReturn:
    raise UnexpectedNetworkCallError("analysis core attempted a network call")


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trap standard-library network entry points reachable from analysis."""

    monkeypatch.setattr(socket, "create_connection", _deny_network)
    monkeypatch.setattr(socket.socket, "connect", _deny_network)
    monkeypatch.setattr(http.client.HTTPConnection, "connect", _deny_network)
    monkeypatch.setattr(http.client.HTTPSConnection, "connect", _deny_network)
    monkeypatch.setattr(urllib.request, "urlopen", _deny_network)


def _document(path: str, text: str, kind: DocumentKind) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, kind)


def test_public_analysis_path_does_not_fetch_hostile_external_targets(no_network: None) -> None:
    document = _document(
        "generated.md",
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
        DocumentKind.MARKDOWN,
    )

    result = check_documents(
        (document,),
        config=Config(scanner=ScannerConfig(inline_math=True)),
    )

    assert result.files_checked == 1
    assert all(
        diagnostic.span is None or diagnostic.span.path == PurePosixPath("generated.md")
        for diagnostic in result.diagnostics
    )


def test_public_analysis_path_remains_offline_for_malformed_notebook_boundary(
    no_network: None,
) -> None:
    notebook = _document(
        "generated.ipynb",
        '{"cells":[{"cell_type":"markdown","source":["See https://example.invalid/x"]}],'
        '"metadata":{},"nbformat":4,"nbformat_minor":5}',
        DocumentKind.NOTEBOOK,
    )

    result = check_documents((notebook,), config=Config())

    assert result.files_checked == 1


def test_no_network_guard_has_a_meaningful_negative_control(no_network: None) -> None:
    with pytest.raises(
        UnexpectedNetworkCallError,
        match="analysis core attempted a network call",
    ):
        socket.create_connection(("example.invalid", 443))
