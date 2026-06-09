from __future__ import annotations

from scieqlint.diag.catalog import CATALOG, explain_code


def test_catalog_has_core_codes() -> None:
    for code in [
        "ALG001",
        "REF002",
        "PARSE021",
        "CFG001",
        "INP002",
        "CFG010",
        "DIM001",
        "DIM002",
        "DIM010",
        "DIM020",
        "SUP001",
        "SCAN010",
    ]:
        assert code in CATALOG
        assert explain_code(code) is not None
