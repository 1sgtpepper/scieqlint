from __future__ import annotations

import ast
import json
from pathlib import Path, PurePosixPath
from typing import cast

from scieqlint.api import check_documents
from scieqlint.config.load import load_config
from scieqlint.config.model import Config
from scieqlint.io.source import DocumentKind, SourceDocument

BENCHMARK_DIR = Path("benchmarks/accuracy")
V010_BENCHMARKS = {
    "algebra.yml",
    "parse_unknown.yml",
    "references.yml",
}


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


def _check_case(path: Path, case: dict[str, object]):
    text = str(case["input"])
    if path.stem in {"algebra", "parse_unknown"}:
        text = f"$$\n{text}\n$$\n"
    document = SourceDocument.from_text(
        PurePosixPath(f"benchmarks/accuracy/{case['id']}.md"),
        text,
        DocumentKind.MARKDOWN,
    )
    return check_documents([document], config=Config())


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
