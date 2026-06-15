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
        "GEN001",
        "REF004",
        "REF005",
        "STR001",
        "STR002",
        "STR003",
        "STR004",
        "STR005",
        "DIR001",
        "DIR002",
        "DIR010",
        "DIR011",
        "DIR012",
    ]:
        assert code in CATALOG
        assert explain_code(code) is not None
