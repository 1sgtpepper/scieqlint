from __future__ import annotations

import ast
import json
import os
from pathlib import Path, PurePosixPath
from typing import cast

import pytest

from scieqlint.api import check_documents
from scieqlint.config.load import load_config
from scieqlint.config.model import Config, ProfileConfig
from scieqlint.io.source import DocumentKind, SourceDocument, SourceOrigin

BENCHMARK_DIR = Path("benchmarks/accuracy")
V010_BENCHMARKS = {
    "algebra.yml",
    "markdown.yml",
    "parse_unknown.yml",
    "references.yml",
}
V110_BENCHMARKS = {"generated.yml"}


def test_v010_accuracy_benchmark_fixtures_are_checked() -> None:
    assert {path.name for path in BENCHMARK_DIR.glob("*.yml")} >= V010_BENCHMARKS

    for path in sorted(BENCHMARK_DIR.glob("*.yml")):
        for case in _load_cases(path):
            if case.get("release") not in {None, "v0.1.0"}:
                continue
            result = _check_case(path, case)
            actual_codes = [diagnostic.code for diagnostic in result.diagnostics]

            assert actual_codes == case["expected_codes"], case["id"]
            assert (result.exit_code() == 0) is case["expected_pass"], case["id"]


def test_v012_dimension_accuracy_benchmark_fixtures_are_checked(tmp_path) -> None:
    path = BENCHMARK_DIR / "dimensions.yml"
    cases = [case for case in _load_cases(path) if case.get("release") == "v0.1.2"]
    assert cases

    for case in cases:
        result = _check_dimension_case(tmp_path, case)
        actual_codes = [diagnostic.code for diagnostic in result.diagnostics]

        assert actual_codes == case["expected_codes"], case["id"]
        assert (result.exit_code() == 0) is case["expected_pass"], case["id"]


def test_v013_latex_accuracy_benchmark_fixtures_are_checked() -> None:
    path = BENCHMARK_DIR / "latex.yml"
    cases = [case for case in _load_cases(path) if case.get("release") == "v0.1.3"]
    assert cases

    for case in cases:
        result = _check_latex_case(case)
        actual_codes = [diagnostic.code for diagnostic in result.diagnostics]

        assert actual_codes == case["expected_codes"], case["id"]
        assert (result.exit_code() == 0) is case["expected_pass"], case["id"]


def test_v014_notebook_accuracy_benchmark_fixtures_are_checked() -> None:
    path = BENCHMARK_DIR / "notebook.yml"
    cases = [case for case in _load_cases(path) if case.get("release") == "v0.1.4"]
    assert cases

    for case in cases:
        result = _check_notebook_case(case)
        actual_codes = [diagnostic.code for diagnostic in result.diagnostics]

        assert actual_codes == case["expected_codes"], case["id"]
        assert (result.exit_code() == 0) is case["expected_pass"], case["id"]


def test_v110_generated_accuracy_benchmark_fixtures_are_checked() -> None:
    path = BENCHMARK_DIR / "generated.yml"
    cases = [case for case in _load_cases(path) if case.get("release") == "v1.1.0"]
    assert cases

    for case in cases:
        result = _check_generated_case(path, case)
        actual_codes = [diagnostic.code for diagnostic in result.diagnostics]

        assert actual_codes == case["expected_codes"], case["id"]
        assert (result.exit_code() == 0) is case["expected_pass"], case["id"]


@pytest.mark.skipif(
    os.environ.get("SCIEQLINT_RELEASE_GATE") != "1",
    reason="stable-release evidence is enforced by the release workflow",
)
def test_stable_release_executes_100_unique_documented_equations(tmp_path: Path) -> None:
    cases: list[tuple[Path, dict[str, object]]] = []
    for path in sorted(BENCHMARK_DIR.glob("*.yml")):
        cases.extend((path, case) for case in _load_cases(path))

    case_ids = [str(case["id"]) for _path, case in cases]
    assert len(case_ids) == len(set(case_ids)), "equation fixture IDs must be globally unique"

    equation_fixture_ids: list[str] = []
    for path, case in cases:
        if path.stem == "dimensions":
            result = _check_dimension_case(tmp_path, case)
        elif path.stem == "latex":
            result = _check_latex_case(case)
        elif path.stem == "notebook":
            result = _check_notebook_case(case)
        elif path.name in V010_BENCHMARKS:
            result = _check_case(path, case)
        elif path.name in V110_BENCHMARKS:
            result = _check_generated_case(path, case)
        else:
            pytest.fail(f"release gate has no executor for benchmark file: {path.name}")
        actual_codes = [diagnostic.code for diagnostic in result.diagnostics]
        assert actual_codes == case["expected_codes"], case["id"]
        assert (result.exit_code() == 0) is case["expected_pass"], case["id"]
        if result.math_blocks_checked > 0:
            equation_fixture_ids.append(str(case["id"]))

    assert len(equation_fixture_ids) >= 100, (
        "stable releases require at least 100 documented equation fixtures; "
        f"found {len(equation_fixture_ids)}"
    )


def _check_case(path: Path, case: dict[str, object]):
    text = str(case["input"])
    if path.stem in {"algebra", "parse_unknown"}:
        text = f"$$\n{text}\n$$\n"
    document = SourceDocument.from_text(
        PurePosixPath(f"benchmarks/accuracy/{case['id']}.md"),
        text,
        DocumentKind.MARKDOWN,
    )
    profile = case.get("profile")
    config = Config(profile=ProfileConfig(name=str(profile))) if profile is not None else Config()
    return check_documents([document], config=config)


def _check_generated_case(path: Path, case: dict[str, object]):
    document = SourceDocument.from_text(
        PurePosixPath(f"{path.parent.as_posix()}/{case['id']}.md"),
        str(case["input"]),
        DocumentKind.MARKDOWN,
        origin=SourceOrigin(source_document_id=f"source/{case['id']}.pdf"),
    )
    return check_documents(
        [document],
        config=Config(
            profile=ProfileConfig(
                name="generated-myst",
                source_kind="pdf",
                conversion_stage="pdf-to-markdown",
            )
        ),
    )


def _check_dimension_case(tmp_path: Path, case: dict[str, object]):
    text = f"$$\n{case['input']}\n$$\n"
    document = SourceDocument.from_text(
        PurePosixPath(f"benchmarks/accuracy/{case['id']}.md"),
        text,
        DocumentKind.MARKDOWN,
    )
    return check_documents([document], config=_dimension_config(tmp_path, case))


def _check_latex_case(case: dict[str, object]):
    documents = [
        SourceDocument.from_text(
            PurePosixPath(f"benchmarks/accuracy/{case['id']}.tex"),
            str(case["input"]),
            DocumentKind.LATEX,
        )
    ]
    markdown_input = case.get("markdown_input")
    if markdown_input is not None:
        documents.append(
            SourceDocument.from_text(
                PurePosixPath(f"benchmarks/accuracy/{case['id']}.md"),
                str(markdown_input),
                DocumentKind.MARKDOWN,
            )
        )
    return check_documents(documents, config=Config())


def _check_notebook_case(case: dict[str, object]):
    document = SourceDocument.from_text(
        PurePosixPath(f"benchmarks/accuracy/{case['id']}.ipynb"),
        json.dumps(cast(dict[str, object], case["input"])),
        DocumentKind.NOTEBOOK,
    )
    return check_documents([document], config=Config())


def _dimension_config(tmp_path: Path, case: dict[str, object]) -> Config:
    vars_data = cast(dict[str, str], case.get("vars", {}))
    unknown_variables = str(case.get("unknown_variables", "warn"))
    config_path = tmp_path / f"{case['id']}.toml"
    lines = [
        "[checks.dimension]",
        'mode = "auto"',
        f'unknown_variables = "{unknown_variables}"',
    ]
    if vars_data:
        lines.append("")
        lines.append("[vars]")
        lines.extend(f'{name} = "{dimension}"' for name, dimension in sorted(vars_data.items()))
    config_path.write_text("\n".join(lines), encoding="utf-8")
    return load_config(config_path)


def _load_cases(path: Path) -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    current: dict[str, object] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("- id:"):
            if current:
                cases.append(current)
            current = {"id": line.removeprefix("- id:").strip()}
            continue
        if not current or ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        current[key] = _parse_value(raw_value.strip())
    if current:
        cases.append(current)
    return cases


def _parse_value(raw_value: str) -> object:
    if raw_value in {"true", "false"}:
        return raw_value == "true"
    if raw_value.startswith(('"', "[", "{")):
        return ast.literal_eval(raw_value)
    return raw_value
