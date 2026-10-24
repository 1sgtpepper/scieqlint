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
        "REF008",
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
        "DIR013",
        "REF010",
    ]:
        assert code in CATALOG
        assert explain_code(code) is not None


def test_explanations_preserve_every_catalog_key_and_metadata() -> None:
    for code, info in CATALOG.items():
        explanation = explain_code(code)

        assert explanation is not None
        assert explanation.startswith(f"{code} ({info.severity.value}, {info.release})\n")
        assert f"Message: {info.message}\n" in explanation
        assert f"Meaning: {info.meaning}" in explanation
        assert explain_code(code.lower()) is None

    assert explain_code("NOPE999") is None


def test_accessibility_diagnostic_names_the_release() -> None:
    assert CATALOG["PORT002"].release == "v1.2.2"
    assert "(warning, v1.2.2)" in (explain_code("PORT002") or "")


def test_typst_portability_diagnostic_names_the_release() -> None:
    assert CATALOG["PORT003"].release == "v1.2.2"
    assert "(warning, v1.2.2)" in (explain_code("PORT003") or "")
