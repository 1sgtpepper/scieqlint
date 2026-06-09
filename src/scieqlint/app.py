"""Application orchestration layer."""

from __future__ import annotations

import fnmatch
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path, PurePosixPath

from scieqlint import __version__
from scieqlint.check.algebra import check_algebra
from scieqlint.check.dimensions import check_dimensions
from scieqlint.check.references import check_references
from scieqlint.check.suppressions import apply_suppressions
from scieqlint.config.load import load_config
from scieqlint.config.model import AlgebraConfig, Config, ParserConfig
from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import CheckResult, Diagnostic, Severity, SourceSpan
from scieqlint.io.discover import discover_files
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.scan.base import EquationLabel, EquationReference, MathBlock
from scieqlint.scan.latex import LatexScanner
from scieqlint.scan.markdown import MarkdownScanner
from scieqlint.scan.notebook import NotebookScanner


def check_paths(
    paths: Sequence[Path | str],
    *,
    config_path: Path | str | None = None,
    no_algebra: bool = False,
    inline_math: bool = False,
    strict_unknowns: bool = False,
    absolute_paths: bool = False,
) -> CheckResult:
    """Load supported files and check them."""
    config = _apply_overrides(
        load_config(config_path),
        no_algebra=no_algebra,
        inline_math=inline_math,
        strict_unknowns=strict_unknowns,
    )
    discovered = _discover_files(paths or [Path(".")], config.ignore.files)
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
                    span=_file_start_span(path, absolute_paths=absolute_paths),
                    detail=str(exc),
                )
            )
            continue
        documents.append(
            SourceDocument.from_text(
                _display_path(path, absolute_paths=absolute_paths),
                text,
                _document_kind(path),
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
    latex_scanner = LatexScanner()
    notebook_scanner = NotebookScanner()
    blocks: list[MathBlock] = []
    labels: list[EquationLabel] = []
    references: list[EquationReference] = []
    diagnostics: list[Diagnostic] = []

    for document in documents:
        if document.kind is DocumentKind.LATEX:
            scan = latex_scanner.scan(document, config)
        elif document.kind is DocumentKind.NOTEBOOK:
            scan = notebook_scanner.scan(document, config)
        else:
            scan = scanner.scan(document, config)
        blocks.extend(scan.blocks)
        labels.extend(scan.labels)
        references.extend(scan.references)
        diagnostics.extend(scan.diagnostics)
        for block in scan.blocks:
            block_diagnostics = check_algebra(block)
            if config.checks.algebra.enabled:
                diagnostics.extend(block_diagnostics)
            else:
                diagnostics.extend(
                    diagnostic
                    for diagnostic in block_diagnostics
                    if diagnostic.code.startswith("PARSE")
                )
            diagnostics.extend(check_dimensions(block, config))

    if config.parser.strict_unknowns:
        diagnostics = [_strict_unknown(diagnostic) for diagnostic in diagnostics]
    if config.checks.references.enabled:
        diagnostics.extend(
            check_references(
                tuple(labels),
                tuple(references),
                blocks=tuple(blocks),
                strict_missing_labels=config.checks.references.missing_label_strict,
            )
        )
    diagnostics = list(apply_suppressions(diagnostics, documents=documents, blocks=blocks))
    return CheckResult(
        diagnostics=tuple(sorted(diagnostics, key=_diagnostic_key)),
        files_checked=len(documents),
        math_blocks_checked=len(blocks),
        config_path=config.path,
        version=__version__,
    )


def _apply_overrides(
    config: Config,
    *,
    no_algebra: bool,
    inline_math: bool,
    strict_unknowns: bool,
) -> Config:
    scanner = (
        replace(config.scanner, inline_math=True)
        if inline_math and not config.scanner.inline_math
        else config.scanner
    )
    algebra = AlgebraConfig(enabled=False) if no_algebra else config.checks.algebra
    checks = replace(config.checks, algebra=algebra)
    parser = (
        ParserConfig(strict_unknowns=True)
        if strict_unknowns and not config.parser.strict_unknowns
        else config.parser
    )
    return replace(config, scanner=scanner, checks=checks, parser=parser)


def _discover_files(
    paths: Sequence[Path | str],
    ignore_patterns: tuple[str, ...],
) -> tuple[Path, ...]:
    explicit_files: list[Path] = []
    discovered_inputs: list[Path | str] = []
    for raw in paths:
        path = Path(raw)
        text = str(raw)
        if not any(ch in text for ch in "*?[") and path.is_file():
            explicit_files.append(path)
        else:
            discovered_inputs.append(raw)

    discovered = _filter_ignored(discover_files(discovered_inputs), ignore_patterns)
    return tuple(sorted({*explicit_files, *discovered}, key=lambda path: path.as_posix()))


def _filter_ignored(paths: Sequence[Path], patterns: tuple[str, ...]) -> tuple[Path, ...]:
    if not patterns:
        return tuple(paths)
    return tuple(path for path in paths if not _is_ignored(path, patterns))


def _is_ignored(path: Path, patterns: tuple[str, ...]) -> bool:
    rel = _display_path(path, absolute_paths=False).as_posix()
    absolute = path.resolve().as_posix()
    return any(
        fnmatch.fnmatchcase(rel, pattern) or fnmatch.fnmatchcase(absolute, pattern)
        for pattern in patterns
    )


def _strict_unknown(diagnostic: Diagnostic) -> Diagnostic:
    if diagnostic.code not in {"PARSE020", "PARSE021", "PARSE022"}:
        return diagnostic
    return replace(diagnostic, severity=Severity.ERROR)


def _display_path(path: Path, *, absolute_paths: bool) -> PurePosixPath:
    if absolute_paths:
        return PurePosixPath(path.resolve().as_posix())
    try:
        return PurePosixPath(path.resolve().relative_to(Path.cwd().resolve()).as_posix())
    except ValueError:
        return PurePosixPath(path.as_posix())


def _document_kind(path: Path) -> DocumentKind:
    match path.suffix.lower():
        case ".tex":
            return DocumentKind.LATEX
        case ".ipynb":
            return DocumentKind.NOTEBOOK
        case _:
            return DocumentKind.MARKDOWN


def _file_start_span(path: Path, *, absolute_paths: bool) -> SourceSpan:
    display_path = _display_path(path, absolute_paths=absolute_paths)
    return SourceSpan(
        path=display_path,
        start=0,
        end=0,
        line=1,
        col=1,
        end_line=1,
        end_col=1,
    )


def _diagnostic_key(diagnostic: Diagnostic) -> tuple[str, int, int, int, str, str]:
    span = diagnostic.span
    if span is None:
        return ("", -1, 0, 0, diagnostic.code, diagnostic.message)
    cell = -1 if span.cell is None else span.cell
    return (
        span.path.as_posix(),
        cell,
        span.line,
        span.col,
        diagnostic.code,
        diagnostic.message,
    )
