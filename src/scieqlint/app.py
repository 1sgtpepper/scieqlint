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
from scieqlint.check.symbols import check_symbols
from scieqlint.config.load import load_config
from scieqlint.config.model import AlgebraConfig, Config, ParserConfig
from scieqlint.diag.baseline import (
    BaselineIdentity,
    apply_baseline,
    baseline_identities_from_json,
)
from scieqlint.diag.catalog import CATALOG
from scieqlint.diag.model import CheckResult, Diagnostic, Severity, SourceSpan
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.engine.structure import StructureEngine
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.graph.export import build_graph
from scieqlint.graph.model import Graph
from scieqlint.io.discover import discover_files
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost
from scieqlint.scan.base import EquationLabel, EquationReference, MathBlock, SymbolDirective
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
    project_root = _project_root(config)
    discovered = _discover_files(
        _input_paths(paths, config, project_root),
        config.ignore.files,
        config.project.order,
        project_root=project_root,
    )
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
    diagnostics_result = tuple(sorted((*diagnostics, *result.diagnostics), key=_diagnostic_key))
    diagnostics_result = apply_baseline(diagnostics_result, _load_baselines(config, project_root))
    return CheckResult(
        diagnostics=diagnostics_result,
        files_checked=len(discovered),
        math_blocks_checked=result.math_blocks_checked,
        config_path=config.path,
        version=__version__,
        show_suppressed=config.report.show_suppressed,
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
    path_order = {document.path.as_posix(): index for index, document in enumerate(documents)}
    blocks: list[MathBlock] = []
    labels: list[EquationLabel] = []
    references: list[EquationReference] = []
    symbol_directives: list[SymbolDirective] = []
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
        symbol_directives.extend(scan.symbol_directives)
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
        markdown_documents = tuple(
            document for document in documents if document.kind is DocumentKind.MARKDOWN
        )
        if markdown_documents:
            query = QueryHost(MySTFrontend().lower(markdown_documents))
            diagnostics.extend(
                diagnostic.to_diagnostic() for diagnostic in ReferenceEngine().run(query)
            )
    if config.checks.symbols.enabled:
        diagnostics.extend(
            check_symbols(
                tuple(blocks),
                tuple(symbol_directives),
                path_order=path_order,
            )
        )
    markdown_documents = tuple(
        document for document in documents if document.kind is DocumentKind.MARKDOWN
    )
    if markdown_documents:
        query = QueryHost(MySTFrontend().lower(markdown_documents))
        diagnostics.extend(
            diagnostic.to_diagnostic() for diagnostic in StructureEngine().run(query)
        )
    diagnostics = list(apply_suppressions(diagnostics, documents=documents, blocks=blocks))
    return CheckResult(
        diagnostics=tuple(sorted(diagnostics, key=_diagnostic_key)),
        files_checked=len(documents),
        math_blocks_checked=len(blocks),
        config_path=config.path,
        version=__version__,
        show_suppressed=config.report.show_suppressed,
    )


def graph_paths(
    paths: Sequence[Path | str],
    *,
    config_path: Path | str | None = None,
) -> Graph:
    """Load supported files and build the label/reference graph."""
    config = load_config(config_path)
    discovered = _discover_files(paths or [Path(".")], config.ignore.files)
    documents: list[SourceDocument] = []
    for path in discovered:
        documents.append(
            SourceDocument.from_text(
                _display_path(path, absolute_paths=False),
                path.read_text(encoding="utf-8"),
                _document_kind(path),
            )
        )
    return graph_documents(documents, config=config)


def graph_documents(
    documents: Sequence[SourceDocument],
    *,
    config: Config,
) -> Graph:
    """Build graph data from already-loaded documents."""
    scanner = MarkdownScanner()
    latex_scanner = LatexScanner()
    notebook_scanner = NotebookScanner()
    labels: list[EquationLabel] = []
    references: list[EquationReference] = []
    for document in documents:
        if document.kind is DocumentKind.LATEX:
            scan = latex_scanner.scan(document, config)
        elif document.kind is DocumentKind.NOTEBOOK:
            scan = notebook_scanner.scan(document, config)
        else:
            scan = scanner.scan(document, config)
        labels.extend(scan.labels)
        references.extend(scan.references)
    return build_graph(tuple(labels), tuple(references))


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
    order_patterns: tuple[str, ...] = (),
    *,
    project_root: Path | None = None,
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

    discovered = _filter_ignored(
        discover_files(discovered_inputs),
        ignore_patterns,
        project_root=project_root,
    )
    return tuple(
        sorted(
            {*explicit_files, *discovered},
            key=lambda path: _path_key(path, order_patterns, project_root=project_root),
        )
    )


def _filter_ignored(
    paths: Sequence[Path],
    patterns: tuple[str, ...],
    *,
    project_root: Path | None = None,
) -> tuple[Path, ...]:
    if not patterns:
        return tuple(paths)
    return tuple(
        path for path in paths if not _is_ignored(path, patterns, project_root=project_root)
    )


def _is_ignored(
    path: Path,
    patterns: tuple[str, ...],
    *,
    project_root: Path | None = None,
) -> bool:
    rel = _project_relative_path(path, project_root)
    absolute = path.resolve().as_posix()
    return any(
        fnmatch.fnmatchcase(rel, pattern) or fnmatch.fnmatchcase(absolute, pattern)
        for pattern in patterns
    )


def _input_paths(
    paths: Sequence[Path | str],
    config: Config,
    project_root: Path,
) -> tuple[Path | str, ...]:
    if paths:
        return tuple(paths)
    if config.project.order:
        return tuple(project_root / pattern for pattern in config.project.order)
    return (Path("."),)


def _project_root(config: Config) -> Path:
    root = Path(config.project.root.as_posix())
    if root.is_absolute():
        return root
    if config.path is None:
        return Path.cwd() / root
    return Path(config.path.as_posix()).parent / root


def _path_key(
    path: Path,
    order_patterns: tuple[str, ...],
    *,
    project_root: Path | None,
) -> tuple[int, str]:
    rel = _project_relative_path(path, project_root)
    absolute = path.resolve().as_posix()
    for index, pattern in enumerate(order_patterns):
        if fnmatch.fnmatchcase(rel, pattern) or fnmatch.fnmatchcase(absolute, pattern):
            return (index, path.as_posix())
    return (len(order_patterns), path.as_posix())


def _project_relative_path(path: Path, project_root: Path | None) -> str:
    if project_root is not None:
        try:
            return path.resolve().relative_to(project_root.resolve()).as_posix()
        except ValueError:
            pass
    return _display_path(path, absolute_paths=False).as_posix()


def _load_baselines(config: Config, project_root: Path) -> frozenset[BaselineIdentity]:
    identities: set[BaselineIdentity] = set()
    for raw in config.baseline.files:
        path = Path(raw)
        if not path.is_absolute():
            path = project_root / path
        identities.update(baseline_identities_from_json(path.read_text(encoding="utf-8")))
    return frozenset(identities)


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
