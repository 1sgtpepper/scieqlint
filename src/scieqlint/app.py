"""Application service layer."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

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
from scieqlint.diag.model import CheckResult, Diagnostic, Severity
from scieqlint.graph.export import build_graph
from scieqlint.graph.model import Graph
from scieqlint.io.load import file_start_span, load_source_document
from scieqlint.io.project import discover_project_files, input_paths, project_root
from scieqlint.io.source import SourceDocument
from scieqlint.scan.base import EquationLabel, EquationReference, MathBlock, SymbolDirective
from scieqlint.scan.dispatch import scan_document


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
    root = project_root(config)
    discovered = discover_project_files(
        input_paths(paths, config, root),
        ignore_patterns=config.ignore.files,
        order_patterns=config.project.order,
        explicit_file_inputs=bool(paths),
        root=root,
    )
    documents: list[SourceDocument] = []
    diagnostics: list[Diagnostic] = []

    for path in discovered:
        try:
            documents.append(load_source_document(path, absolute_paths=absolute_paths))
        except OSError as exc:
            info = CATALOG["INP001"]
            diagnostics.append(
                Diagnostic(
                    code=info.code,
                    severity=info.severity,
                    message=f"{info.message}: {path}",
                    span=file_start_span(path, absolute_paths=absolute_paths),
                    detail=str(exc),
                )
            )

    result = check_documents(documents, config=config)
    diagnostics_result = tuple(sorted((*diagnostics, *result.diagnostics), key=_diagnostic_key))
    diagnostics_result = apply_baseline(diagnostics_result, _load_baselines(config, root))
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
    path_order = {document.path.as_posix(): index for index, document in enumerate(documents)}
    blocks: list[MathBlock] = []
    labels: list[EquationLabel] = []
    references: list[EquationReference] = []
    symbol_directives: list[SymbolDirective] = []
    diagnostics: list[Diagnostic] = []

    for document in documents:
        scan = scan_document(document, config)
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
    if config.checks.symbols.enabled:
        diagnostics.extend(
            check_symbols(
                tuple(blocks),
                tuple(symbol_directives),
                path_order=path_order,
            )
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
    root = project_root(config)
    discovered = discover_project_files(
        input_paths(paths, config, root),
        ignore_patterns=config.ignore.files,
        order_patterns=config.project.order,
        explicit_file_inputs=bool(paths),
        root=root,
    )
    documents: list[SourceDocument] = []
    for path in discovered:
        documents.append(load_source_document(path, absolute_paths=False))
    return graph_documents(documents, config=config)


def graph_documents(
    documents: Sequence[SourceDocument],
    *,
    config: Config,
) -> Graph:
    """Build graph data from already-loaded documents."""
    labels: list[EquationLabel] = []
    references: list[EquationReference] = []
    for document in documents:
        scan = scan_document(document, config)
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
