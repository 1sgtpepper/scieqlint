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
        "GEN002",
        "GEN003",
        "GEN004",
        "GEN005",
        "REF004",
        "REF005",
        "REF007",
        "REF011",
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


def test_new_accessibility_diagnostic_does_not_claim_a_published_release() -> None:
    assert CATALOG["PORT002"].release == "Unreleased"
    assert "(warning, Unreleased)" in (explain_code("PORT002") or "")


def test_typst_portability_diagnostic_is_cataloged_for_the_current_release() -> None:
    assert CATALOG["PORT003"].release == "v1.1.0"
    assert "(warning, v1.1.0)" in (explain_code("PORT003") or "")
