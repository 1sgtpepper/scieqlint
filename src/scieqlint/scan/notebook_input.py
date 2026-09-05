"""Compatibility exports for the transitional notebook scanner.

The notebook JSON DTO and source-span mapping are owned by the frontend layer. The
scanner keeps this module as a narrow compatibility seam for existing imports.
"""

from scieqlint.frontend.notebook_input import (
    NotebookInput,
    NotebookSourceLocationError,
    cell_source,
    input_diagnostic,
    map_notebook_span,
    parse_notebook_input,
    schema_diagnostic,
)

__all__ = (
    "NotebookInput",
    "NotebookSourceLocationError",
    "cell_source",
    "input_diagnostic",
    "map_notebook_span",
    "parse_notebook_input",
    "schema_diagnostic",
)
