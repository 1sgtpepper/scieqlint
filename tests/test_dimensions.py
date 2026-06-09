from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.api import check_documents
from scieqlint.config.load import load_config
from scieqlint.config.model import Config
from scieqlint.diag.model import CheckResult, Diagnostic
from scieqlint.io.source import DocumentKind, SourceDocument


def test_zero_config_dimension_check_is_quiet() -> None:
    result = _check("$$\nF = m*a\n$$\n", Config())

    assert result.diagnostics == ()


def test_configured_mechanics_dimensions_pass(tmp_path) -> None:
    config = _mechanics_config(tmp_path)

    result = _check("$$\nF = m*a\n$$\n", config)

    assert result.diagnostics == ()


def test_configured_equation_dimension_mismatch_reports_dim001(tmp_path) -> None:
    config = _mechanics_config(tmp_path)

    result = _check("$$\nE = m*c\n$$\n", config)

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["DIM001"]
    assert result.diagnostics[0].detail == "left dimension M L^2 T^-2; right dimension M L T^-1"


def test_configured_equation_dimension_match_with_power_passes(tmp_path) -> None:
    config = _mechanics_config(tmp_path)

    result = _check("$$\nE = m*c^2\n$$\n", config)

    assert result.diagnostics == ()


def test_configured_aliases_normalize_before_dimension_lookup(tmp_path) -> None:
    config = _mechanics_config(
        tmp_path,
        aliases=[
            'F = ["\\\\mathcalF"]',
            'm = ["mass"]',
            'a = ["accel"]',
        ],
    )

    result = _check("$$\n\\mathcalF = mass*accel\n$$\n", config)

    assert [diagnostic.code for diagnostic in _dimension_diagnostics(result)] == []


def test_configured_unicode_alias_normalizes_before_dimension_lookup(tmp_path) -> None:
    config = _mechanics_config(tmp_path, aliases=['theta = ["θ"]'], extra_vars=['theta = "1"'])

    result = _check("$$\nθ + 1 = theta\n$$\n", config)

    assert [diagnostic.code for diagnostic in _dimension_diagnostics(result)] == []


def test_configured_punctuation_alias_normalizes_before_dimension_lookup(tmp_path) -> None:
    config = _mechanics_config(
        tmp_path, aliases=['speed = ["v."]'], extra_vars=['speed = "L T^-1"']
    )

    result = _check("$$\nv. = speed\n$$\n", config)

    assert [diagnostic.code for diagnostic in _dimension_diagnostics(result)] == []


def test_unaliased_tex_command_keeps_skipped_dimension_behavior(tmp_path) -> None:
    config = _mechanics_config(tmp_path)

    result = _check("$$\nF = \\mathcalF\n$$\n", config)

    assert [diagnostic.code for diagnostic in _dimension_diagnostics(result)] == ["DIM020"]


def test_unaliased_unicode_symbol_keeps_skipped_dimension_behavior(tmp_path) -> None:
    config = _mechanics_config(tmp_path)

    result = _check("$$\nF = ρ*a\n$$\n", config)

    assert [diagnostic.code for diagnostic in _dimension_diagnostics(result)] == ["DIM020"]


def test_dimension_check_ignores_expression_without_equality(tmp_path) -> None:
    config = _mechanics_config(tmp_path)

    result = _check("$$\nF\n$$\n", config)

    assert result.diagnostics == ()


def test_configured_dimensions_support_tex_multiply_and_implicit_products(tmp_path) -> None:
    config = _mechanics_config(tmp_path)

    result = _check("$$\nF = m \\cdot a = m \\times a = m a\n$$\n", config)

    assert result.diagnostics == ()


def test_configured_dimensions_support_division_fraction_and_square_root(tmp_path) -> None:
    config = _mechanics_config(tmp_path)

    result = _check("$$\nc = x/t = \\frac{x}{t} = \\sqrt{E/m}\n$$\n", config)

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["PARSE020"]
    assert [
        diagnostic.code for diagnostic in result.diagnostics if diagnostic.rule == "dimensions"
    ] == []


def test_configured_dimensions_support_signed_exponents(tmp_path) -> None:
    config = _mechanics_config(tmp_path)

    result = _check("$$\na = x*t^(-2) = x*t^-2 = x*t^(+1)*t^-3\n$$\n", config)

    assert result.diagnostics == ()


def test_configured_addition_dimension_mismatch_reports_dim002(tmp_path) -> None:
    config = _mechanics_config(tmp_path)

    result = _check("$$\nx + t = x\n$$\n", config)

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["DIM002"]


def test_unknown_symbol_warns_only_when_policy_warns(tmp_path) -> None:
    warn_config = _mechanics_config(tmp_path, unknown_variables="warn")
    ignore_config = _mechanics_config(tmp_path, unknown_variables="ignore")

    warn_result = _check("$$\nF = m*j\n$$\n", warn_config)
    ignore_result = _check("$$\nF = m*j\n$$\n", ignore_config)

    assert [diagnostic.code for diagnostic in warn_result.diagnostics] == ["DIM010"]
    assert warn_result.diagnostics[0].detail == "j"
    assert ignore_result.diagnostics == ()


def test_malformed_dimension_expression_reports_skipped_check(tmp_path) -> None:
    config = _mechanics_config(tmp_path)

    result = _check("$$\nF = m @ a\n$$\n", config)

    assert "DIM020" in [diagnostic.code for diagnostic in result.diagnostics]


def test_unbalanced_dimension_group_reports_skipped_check(tmp_path) -> None:
    config = _mechanics_config(tmp_path)

    result = _check("$$\nF = (m*a\n$$\n", config)

    assert "DIM020" in [diagnostic.code for diagnostic in result.diagnostics]


def test_odd_square_root_dimension_reports_skipped_check(tmp_path) -> None:
    config = _mechanics_config(tmp_path)

    result = _check("$$\nx = \\sqrt{x}\n$$\n", config)

    assert "DIM020" in [diagnostic.code for diagnostic in result.diagnostics]


def _check(text: str, config: Config):
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        text,
        DocumentKind.MARKDOWN,
    )
    return check_documents([document], config=config)


def _dimension_diagnostics(result: CheckResult) -> tuple[Diagnostic, ...]:
    return tuple(diagnostic for diagnostic in result.diagnostics if diagnostic.rule == "dimensions")


def _mechanics_config(
    tmp_path,
    *,
    unknown_variables: str = "warn",
    aliases: list[str] | None = None,
    extra_vars: list[str] | None = None,
) -> Config:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text(
        "\n".join(
            [
                "[checks.algebra]",
                "enabled = false",
                "",
                "[checks.dimension]",
                'mode = "on"',
                f'unknown_variables = "{unknown_variables}"',
                "",
                "[vars]",
                'm = "M"',
                'a = "L T^-2"',
                'c = "L T^-1"',
                'F = "M L T^-2"',
                'E = "M L^2 T^-2"',
                'x = "L"',
                't = "T"',
                *(extra_vars or []),
                *(_aliases_section(aliases or [])),
            ]
        ),
        encoding="utf-8",
    )
    return load_config(config_path)


def _aliases_section(aliases: list[str]) -> list[str]:
    if not aliases:
        return []
    return ["", "[aliases]", *aliases]
