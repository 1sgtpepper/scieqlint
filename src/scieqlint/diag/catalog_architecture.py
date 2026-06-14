"""Architecture diagnostic catalog extension.

The first implementation keeps these entries separate from the stable v0.1
catalog so the architecture slice can be reviewed without forcing one large
catalog merge. A later integration PR can install or copy these entries into
``scieqlint.diag.catalog`` once the codes are accepted.
"""

from __future__ import annotations

from scieqlint.diag.catalog import CATALOG, DiagnosticInfo
from scieqlint.diag.model import Severity


def _info(
    code: str,
    severity: Severity,
    message: str,
    meaning: str,
) -> DiagnosticInfo:
    return DiagnosticInfo(code, severity, message, "v0.2.0", meaning)


ARCHITECTURE_CATALOG: dict[str, DiagnosticInfo] = {
    "STR001": _info(
        "STR001",
        Severity.WARNING,
        "ATX heading marker must be followed by a space",
        "A MyST/Markdown ATX heading such as '####Title' is malformed.",
    ),
    "STR002": _info(
        "STR002",
        Severity.WARNING,
        "fenced block is missing its closing delimiter",
        "A generic fenced block appears to be unterminated.",
    ),
    "STR003": _info(
        "STR003",
        Severity.INFO,
        "fenced code block has no language/info string",
        "A generic fenced code block lacks a language/info string under an active profile.",
    ),
    "STR004": _info(
        "STR004",
        Severity.INFO,
        "section hierarchy skips a heading level",
        "A heading outline jumps by more than one level.",
    ),
    "DIR010": _info(
        "DIR010",
        Severity.WARNING,
        "code-cell directive is missing an executable language",
        "A MyST code-cell directive has no language/engine argument.",
    ),
    "REF010": _info(
        "REF010",
        Severity.ERROR,
        "duplicate MyST target anchor",
        "A generic MyST target anchor is defined more than once.",
    ),
    "REF011": _info(
        "REF011",
        Severity.WARNING,
        "generic reference target not found",
        "A generic `{ref}` or markdown label link cannot be resolved.",
    ),
    "REF012": _info(
        "REF012",
        Severity.WARNING,
        "generic reference target is ambiguous",
        "A reference target resolves to more than one candidate.",
    ),
    "REF013": _info(
        "REF013",
        Severity.WARNING,
        "MyST target anchor is not attached to a following block",
        "A `(label)=` anchor is not associated with a following heading/block.",
    ),
    "REF014": _info(
        "REF014",
        Severity.ERROR,
        "generated document dropped required MyST anchor",
        "A generated output is missing a source anchor needed for references.",
    ),
    "GEN001": _info(
        "GEN001",
        Severity.WARNING,
        "generated document is missing provenance metadata",
        "Generated-document validation was requested without source/generated pairing metadata.",
    ),
    "GEN002": _info(
        "GEN002",
        Severity.ERROR,
        "source/generated target inventories differ",
        "A generated document does not preserve its source target inventory.",
    ),
    "GEN003": _info(
        "GEN003",
        Severity.ERROR,
        "generated document introduced or preserved unresolved reference",
        "A generated document has unresolved references after conversion/translation.",
    ),
    "GEN004": _info(
        "GEN004",
        Severity.ERROR,
        "generated formula contains suspiciously spaced tokens",
        "A generated formula appears to have been split into character-level text.",
    ),
    "GEN005": _info(
        "GEN005",
        Severity.ERROR,
        "generated formula contains an unresolved placeholder",
        "A generated formula placeholder reached lint output instead of math source.",
    ),
    "GEN006": _info(
        "GEN006",
        Severity.ERROR,
        "generated formula contains a garbled extraction marker",
        "A generated formula includes deterministic extraction-artifact markers.",
    ),
    "MATH020": _info(
        "MATH020",
        Severity.INFO,
        "unsupported or unknown math",
        "MathHost classified a math span as unknown/unsupported.",
    ),
    "MATH021": _info(
        "MATH021",
        Severity.WARNING,
        "display math contains multiple labels",
        "A display math container has multiple labels that may not be portable.",
    ),
    "PROJ001": _info(
        "PROJ001",
        Severity.WARNING,
        "referenced file is not a project member",
        "A reference points to a file outside the active project graph.",
    ),
    "PROJ002": _info(
        "PROJ002",
        Severity.WARNING,
        "project file appears under multiple normalized paths",
        "Project graph membership contains path aliases after normalization.",
    ),
    "PROJ003": _info(
        "PROJ003",
        Severity.WARNING,
        "included content references hidden or excluded labels",
        "A public document references labels in hidden or excluded project files.",
    ),
    "PORT001": _info(
        "PORT001",
        Severity.INFO,
        "inline math has no portable alt text",
        "Inline math may need alt text under accessibility/output profiles.",
    ),
    "PORT002": _info(
        "PORT002",
        Severity.WARNING,
        "display math has no portable alt text",
        "Display math may need alt text under accessibility/output profiles.",
    ),
    "PORT003": _info(
        "PORT003",
        Severity.WARNING,
        "Quarto cross-reference label has no recognized type prefix",
        "A Quarto cross-reference label lacks a prefix such as fig-/tbl-/eq-.",
    ),
    "PORT004": _info(
        "PORT004",
        Severity.WARNING,
        "Quarto cell combines renderings with crossref-producing options",
        "A Quarto cell combines renderings with options that create crossrefs.",
    ),
}


def install_architecture_catalog() -> None:
    """Install architecture-preview codes into the process-local catalog."""

    CATALOG.update(ARCHITECTURE_CATALOG)
