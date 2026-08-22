from __future__ import annotations

import http.client
import socket
import urllib.request
from pathlib import PurePosixPath
from typing import NoReturn

import pytest

from scieqlint.api import check_documents, check_paths
from scieqlint.config.model import Config, ScannerConfig
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.markdown import MarkdownScanner


class UnexpectedNetworkCallError(AssertionError):
    """Raised when deterministic analysis attempts to open a network connection."""


def _deny_network(*_args: object, **_kwargs: object) -> NoReturn:
    raise UnexpectedNetworkCallError("analysis core attempted a network call")


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


def _document(path: str, text: str, kind: DocumentKind) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, kind)


def test_public_analysis_path_keeps_hostile_external_destinations_inert(
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
                ("[See {eq}`active-label`](https://example.invalid/{eq}`destination-target`)."),
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
    assert [
        (
            diagnostic.code,
            diagnostic.message,
            diagnostic.span.line if diagnostic.span is not None else None,
            diagnostic.span.col if diagnostic.span is not None else None,
        )
        for diagnostic in result.diagnostics
        if diagnostic.code.startswith("REF")
    ] == [
        (
            "REF002",
            "equation reference target not found: active-label",
            5,
            11,
        )
    ]
    assert all(
        diagnostic.span is None or diagnostic.span.path == PurePosixPath(input_path.as_posix())
        for diagnostic in result.diagnostics
    )


def test_public_analysis_path_ignores_fenced_math_content(
    no_network: None,
) -> None:
    document = _document(
        "safe.md",
        "\n".join(
            (
                "# Safe",
                "",
                "```{code-cell} python",
                "ignored = '$z = 1$'",
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

    active_control = _document(
        "active.md",
        "ignored = '$z = 1$'\n\nInline math: $x = y$.",
        DocumentKind.MARKDOWN,
    )
    active_result = check_documents(
        (active_control,),
        config=Config(scanner=ScannerConfig(inline_math=True)),
    )
    assert active_result.math_blocks_checked == 2


@pytest.mark.parametrize(
    ("digits", "expected_dimension_codes"),
    [(512, ()), (513, ("DIM020", "DIM020"))],
    ids=["at-budget", "over-budget"],
)
def test_public_analysis_path_fails_closed_at_dimension_budget(
    tmp_path,
    no_network: None,
    digits: int,
    expected_dimension_codes: tuple[str, ...],
) -> None:
    config_path = tmp_path / "budget.toml"
    config_path.write_text(
        '[checks.dimension]\nmode = "on"\n\n[vars]\nx = "L"\n',
        encoding="utf-8",
    )
    input_path = tmp_path / "budget.md"
    exponent = "9" * digits
    equation = f"x^{exponent}=x^{exponent}"
    input_path.write_text(f"$$\n{equation}\n$$\n", encoding="utf-8")

    result = check_paths(
        (input_path,),
        config_path=config_path,
        absolute_paths=True,
    )

    assert result.files_checked == 1
    assert [
        diagnostic.code for diagnostic in result.diagnostics if diagnostic.rule == "dimensions"
    ] == list(expected_dimension_codes)
    if expected_dimension_codes:
        dimension_diagnostic = next(
            diagnostic for diagnostic in result.diagnostics if diagnostic.rule == "dimensions"
        )
        assert dimension_diagnostic.detail == (
            "dimension expression exceeds the supported numeric-component budget "
            "of 512 decimal digits"
        )


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


def test_public_analysis_path_reports_unreadable_input(
    tmp_path,
    no_network: None,
) -> None:
    unreadable = tmp_path / "unreadable.md"
    unreadable.write_bytes(b"\xff")

    result = check_paths((unreadable,), absolute_paths=True)

    assert result.files_checked == 1
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["INP001"]
    assert result.diagnostics[0].span is not None
    assert result.diagnostics[0].span.path == PurePosixPath(unreadable.as_posix())


def test_no_network_guard_has_a_meaningful_negative_control(
    no_network: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_scan = MarkdownScanner.scan

    def scan_then_attempt_network(scanner, document, config):
        result = original_scan(scanner, document, config)
        socket.create_connection(("example.invalid", 443))
        return result

    monkeypatch.setattr(MarkdownScanner, "scan", scan_then_attempt_network)

    with pytest.raises(
        UnexpectedNetworkCallError,
        match="analysis core attempted a network call",
    ):
        check_documents(
            (_document("negative.md", "Inline math: $x = y$.", DocumentKind.MARKDOWN),),
            config=Config(scanner=ScannerConfig(inline_math=True)),
        )
