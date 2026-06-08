from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.api import check_documents
from scieqlint.config.load import load_config
from scieqlint.config.model import Config
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


def _check(text: str, config: Config):
    document = SourceDocument.from_text(
        PurePosixPath("paper.md"),
        text,
        DocumentKind.MARKDOWN,
    )
    return check_documents([document], config=config)


def _mechanics_config(tmp_path, *, unknown_variables: str = "warn") -> Config:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text(
        "\n".join(
            [
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
            ]
        ),
        encoding="utf-8",
    )
    return load_config(config_path)
