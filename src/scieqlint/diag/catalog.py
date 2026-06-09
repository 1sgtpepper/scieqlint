"""Diagnostic catalog."""

from __future__ import annotations

from dataclasses import dataclass

from scieqlint.diag.model import Severity


@dataclass(frozen=True, slots=True)
class DiagnosticInfo:
    code: str
    severity: Severity
    message: str
    release: str
    meaning: str


CATALOG: dict[str, DiagnosticInfo] = {
    "ALG001": DiagnosticInfo(
        "ALG001",
        Severity.ERROR,
        "algebraic identity does not hold",
        "v0.1.0",
        "Adjacent equality sides are proven unequal within the supported scalar algebra subset.",
    ),
    "ALG010": DiagnosticInfo(
        "ALG010",
        Severity.WARNING,
        "identity assumes nonzero denominator",
        "v0.1.0",
        "The identity may require denominator assumptions.",
    ),
    "ALG020": DiagnosticInfo(
        "ALG020",
        Severity.INFO,
        "algebra check skipped",
        "v0.1.0",
        "The expression was not checked by algebra.",
    ),
    "ALG030": DiagnosticInfo(
        "ALG030",
        Severity.WARNING,
        "algebra check exceeded configured limit",
        "v0.1.0",
        "The algebra check stopped because a configured limit was reached.",
    ),
    "PARSE001": DiagnosticInfo(
        "PARSE001",
        Severity.WARNING,
        "could not parse supported-looking math",
        "v0.1.0",
        "The parser could not parse math that looked like it might be in scope.",
    ),
    "PARSE020": DiagnosticInfo(
        "PARSE020",
        Severity.INFO,
        "unsupported syntax; check skipped",
        "v0.1.0",
        "The expression uses syntax outside the supported subset.",
    ),
    "PARSE021": DiagnosticInfo(
        "PARSE021",
        Severity.INFO,
        "unsupported function; check skipped",
        "v0.1.0",
        "The expression uses a function outside the supported subset.",
    ),
    "PARSE022": DiagnosticInfo(
        "PARSE022",
        Severity.INFO,
        "unsupported operator; check skipped",
        "v0.1.0",
        "The expression uses an operator outside the supported subset.",
    ),
    "SCAN001": DiagnosticInfo(
        "SCAN001",
        Severity.WARNING,
        "unterminated math container",
        "v0.1.0",
        "A display math container appears to be missing its closing delimiter.",
    ),
    "SCAN002": DiagnosticInfo(
        "SCAN002",
        Severity.INFO,
        "inline math skipped by config",
        "v0.1.0",
        "Inline math was found but inline scanning is disabled.",
    ),
    "SCAN010": DiagnosticInfo(
        "SCAN010",
        Severity.WARNING,
        "malformed symbol directive",
        "v1.0.0",
        "An explicit scieqlint-symbol directive could not be parsed.",
    ),
    "INP001": DiagnosticInfo(
        "INP001",
        Severity.ERROR,
        "file could not be read or decoded",
        "v0.1.0",
        "The file could not be read as configured.",
    ),
    "INP002": DiagnosticInfo(
        "INP002",
        Severity.WARNING,
        "notebook schema issue",
        "v0.1.4",
        "A notebook shape is invalid or incomplete, but readable cells may still be scanned.",
    ),
    "INP003": DiagnosticInfo(
        "INP003",
        Severity.WARNING,
        "file exceeded configured limit",
        "v0.1.0",
        "The file was skipped because it exceeded a configured limit.",
    ),
    "CFG001": DiagnosticInfo(
        "CFG001",
        Severity.ERROR,
        "invalid config file",
        "v0.1.0",
        "The config file is invalid.",
    ),
    "CFG010": DiagnosticInfo(
        "CFG010",
        Severity.ERROR,
        "invalid dimension expression",
        "v0.1.2",
        "A configured dimension expression is invalid.",
    ),
    "DIM001": DiagnosticInfo(
        "DIM001",
        Severity.ERROR,
        "equation sides have different dimensions",
        "v0.1.2",
        "Adjacent equality sides have incompatible configured dimensions.",
    ),
    "DIM002": DiagnosticInfo(
        "DIM002",
        Severity.ERROR,
        "addition combines incompatible dimensions",
        "v0.1.2",
        "Addition or subtraction combines terms with incompatible configured dimensions.",
    ),
    "DIM010": DiagnosticInfo(
        "DIM010",
        Severity.WARNING,
        "unknown variable dimension",
        "v0.1.2",
        "A symbol has no configured dimension while dimension checking is active.",
    ),
    "DIM020": DiagnosticInfo(
        "DIM020",
        Severity.INFO,
        "dimension check skipped",
        "v0.1.2",
        "Dimension checking skipped an expression outside the supported subset.",
    ),
    "SYM001": DiagnosticInfo(
        "SYM001",
        Severity.WARNING,
        "undefined symbol",
        "v1.0.0",
        "A symbol is used before an explicit scieqlint-symbol directive defines it.",
    ),
    "REF001": DiagnosticInfo(
        "REF001",
        Severity.ERROR,
        "duplicate equation label",
        "v0.1.0",
        "The same equation label appears more than once.",
    ),
    "REF002": DiagnosticInfo(
        "REF002",
        Severity.WARNING,
        "missing equation reference target",
        "v0.1.0",
        "A supported equation reference points to a missing target.",
    ),
    "REF003": DiagnosticInfo(
        "REF003",
        Severity.INFO,
        "missing equation label in strict mode",
        "v0.1.0",
        "An equation block has no label while strict label mode is enabled.",
    ),
    "SUP001": DiagnosticInfo(
        "SUP001",
        Severity.WARNING,
        "unknown suppression code",
        "v0.2.0",
        "A suppression comment names a diagnostic code that is not in the catalog.",
    ),
}


def explain_code(code: str) -> str | None:
    """Return human-readable explanation text for a diagnostic code."""
    info = CATALOG.get(code)
    if info is None:
        return None
    return (
        f"{info.code} ({info.severity.value}, {info.release})\n"
        f"Message: {info.message}\n"
        f"Meaning: {info.meaning}"
    )
