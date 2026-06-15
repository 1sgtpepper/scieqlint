from __future__ import annotations

from pathlib import Path, PurePosixPath

from scieqlint.api import check_documents
from scieqlint.config.load import load_config
from scieqlint.config.model import Config
from scieqlint.diag.model import Severity
from scieqlint.io.source import DocumentKind, SourceDocument


def test_release_fixture_covers_mechanics_preset() -> None:
    path = Path("tests/fixtures/bad/preset_mechanics_bad.md")
    result = _check_fixture(path, config=load_config(preset="mechanics"))

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["DIM001"]
    assert result.diagnostics[0].detail == ("left dimension M L^2 T^-2; right dimension M L T^-1")


def test_release_fixture_covers_generated_myst_preset(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    path = Path(__file__).parent / "fixtures/bad/generated_myst_profile_bad.md"
    result = _check_fixture(path, config=load_config(preset="generated-myst"))

    assert {diagnostic.code for diagnostic in result.diagnostics} == {
        "ALG001",
        "PARSE021",
        "REF001",
        "REF002",
        "SCAN001",
    }
    error_codes = {
        diagnostic.code
        for diagnostic in result.diagnostics
        if diagnostic.severity is Severity.ERROR
    }
    assert error_codes == {
        "ALG001",
        "PARSE021",
        "REF001",
    }


def test_release_fixture_covers_alias_dimension_normalization(tmp_path) -> None:
    config_path = tmp_path / "scieqlint.toml"
    config_path.write_text(
        "\n".join(
            [
                "[checks.dimension]",
                'mode = "on"',
                "",
                "[vars]",
                'F = "M L T^-2"',
                'm = "M"',
                'a = "L T^-2"',
                "",
                "[aliases]",
                'F = ["force"]',
                'm = ["mass"]',
                'a = ["accel"]',
            ]
        ),
        encoding="utf-8",
    )

    path = Path("tests/fixtures/good/alias_dimensions_good.md")
    result = _check_fixture(path, config=load_config(config_path))

    assert result.diagnostics == ()


def _check_fixture(path: Path, *, config: Config):
    return check_documents(
        [
            SourceDocument.from_text(
                PurePosixPath(path.as_posix()),
                path.read_text(encoding="utf-8"),
                DocumentKind.MARKDOWN,
            )
        ],
        config=config,
    )
