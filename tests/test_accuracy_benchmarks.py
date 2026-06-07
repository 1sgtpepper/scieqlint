from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath

from scieqlint.api import check_documents
from scieqlint.config.model import Config
from scieqlint.io.source import DocumentKind, SourceDocument

BENCHMARK_DIR = Path("benchmarks/accuracy")
V010_BENCHMARKS = {
    "algebra.yml",
    "parse_unknown.yml",
    "references.yml",
}


def test_v010_accuracy_benchmark_fixtures_are_checked() -> None:
    assert V010_BENCHMARKS <= {path.name for path in BENCHMARK_DIR.glob("*.yml")}

    for path in sorted(BENCHMARK_DIR.glob("*.yml")):
        for case in _load_cases(path):
            if case.get("release") not in {None, "v0.1.0"}:
                continue
            result = _check_case(path, case)
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
    if raw_value.startswith(('"', "[")):
        return ast.literal_eval(raw_value)
    return raw_value
