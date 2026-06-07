"""Application orchestration layer."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from scieqlint import __version__
from scieqlint.check.algebra import check_algebra
from scieqlint.check.references import check_references
from scieqlint.config.load import load_config
from scieqlint.config.model import Config
from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import CheckResult, Diagnostic, SourceSpan
from scieqlint.io.discover import discover_files
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.base import EquationLabel, EquationReference, MathBlock
from scieqlint.scan.markdown import MarkdownScanner


def check_paths(
    paths: Sequence[Path | str],
    *,
    config_path: Path | str | None = None,
) -> CheckResult:
    """Load supported files and check them."""
    config = load_config(config_path)
    discovered = discover_files(paths or [Path(".")])
    documents: list[SourceDocument] = []
    diagnostics: list[Diagnostic] = []

    for path in discovered:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            info = CATALOG["INP001"]
            diagnostics.append(
                Diagnostic(
                    code=info.code,
                    severity=info.severity,
                    message=f"{info.message}: {path}",
                    span=_file_start_span(path),
                    detail=str(exc),
                )
            )
            continue
        documents.append(
            SourceDocument.from_text(
                _display_path(path),
                text,
                DocumentKind.MARKDOWN,
            )
        )

    result = check_documents(documents, config=config)
    return CheckResult(
        diagnostics=tuple(sorted((*diagnostics, *result.diagnostics), key=_diagnostic_key)),
        files_checked=len(discovered),
        math_blocks_checked=result.math_blocks_checked,
        config_path=config.path,
        version=__version__,
    )


def check_documents(
    documents: Sequence[SourceDocument],
    *,
    config: Config,
) -> CheckResult:
    """Check already-loaded documents."""
    scanner = MarkdownScanner()
    blocks: list[MathBlock] = []
    labels: list[EquationLabel] = []
    references: list[EquationReference] = []
    diagnostics: list[Diagnostic] = []

    for document in documents:
        scan = scanner.scan(document, config)
        blocks.extend(scan.blocks)
        labels.extend(scan.labels)
        references.extend(scan.references)
        diagnostics.extend(scan.diagnostics)
        if config.checks.algebra.enabled:
            for block in scan.blocks:
                diagnostics.extend(check_algebra(block))

    if config.checks.references.enabled:
        diagnostics.extend(
            check_references(
                tuple(labels),
                tuple(references),
                blocks=tuple(blocks),
                strict_missing_labels=config.checks.references.missing_label_strict,
            )
        )
    return CheckResult(
        diagnostics=tuple(sorted(diagnostics, key=_diagnostic_key)),
        files_checked=len(documents),
        math_blocks_checked=len(blocks),
        config_path=config.path,
        version=__version__,
    )


def _display_path(path: Path) -> PurePosixPath:
    try:
        return PurePosixPath(path.resolve().relative_to(Path.cwd().resolve()).as_posix())
    except ValueError:
        return PurePosixPath(path.as_posix())


def _file_start_span(path: Path) -> SourceSpan:
    display_path = _display_path(path)
    return SourceSpan(
        path=display_path,
        start=0,
        end=0,
        line=1,
        col=1,
        end_line=1,
        end_col=1,
    )


def _diagnostic_key(diagnostic: Diagnostic) -> tuple[str, int, int, str]:
    span = diagnostic.span
    if span is None:
        return ("", 0, 0, diagnostic.code)
    return (span.path.as_posix(), span.line, span.col, diagnostic.code)
