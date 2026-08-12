from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_scanner() -> ModuleType:
    path = Path("tools/architecture/terminology_drift.py")
    spec = importlib.util.spec_from_file_location("_terminology_drift_issue_262", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


terminology_drift = _load_scanner()


def test_exact_length_fences_remain_opaque_and_preserve_line_numbers() -> None:
    source = (
        "# Architecture\n\n"
        "```text\n"
        "workspace host\n"
        "```\n"
        "WorkspaceHost\n"
        "~~~text\n"
        "frontend host\n"
        "~~~\n"
    )

    stripped = terminology_drift.strip_markdown_code(source)

    assert stripped.count("\n") == source.count("\n")
    assert "workspace host" not in stripped
    assert "frontend host" not in stripped
    assert "WorkspaceHost" in stripped


def test_exact_length_fix_does_not_change_adjacent_fence_semantics() -> None:
    unmatched = "# Architecture\n\n```text\nworkspace host\n"
    longer_closer = "```text\nworkspace host\n````\n"
    indented = " ```text\nworkspace host\n ```\n"

    assert terminology_drift.strip_markdown_code(unmatched) == unmatched
    assert "workspace host" in terminology_drift.strip_markdown_code(longer_closer)
    assert terminology_drift.strip_markdown_code(indented) == indented


def test_each_line_is_classified_once(monkeypatch: pytest.MonkeyPatch) -> None:
    source = "".join(f"```{index}\n" for index in range(2_000))
    calls = 0
    original_opener = terminology_drift._exact_fence_opener
    original_closer = terminology_drift._is_exact_fence_closer

    def counted_opener(line: str) -> tuple[str, int] | None:
        nonlocal calls
        calls += 1
        return original_opener(line)

    def counted_closer(line: str, opener: tuple[str, int]) -> bool:
        nonlocal calls
        calls += 1
        return original_closer(line, opener)

    monkeypatch.setattr(terminology_drift, "_exact_fence_opener", counted_opener)
    monkeypatch.setattr(terminology_drift, "_is_exact_fence_closer", counted_closer)

    terminology_drift.strip_markdown_code(source)

    assert calls == len(source.splitlines(keepends=True))


def test_closer_classification_does_not_rebuild_the_opener_marker() -> None:
    class Marker(str):
        def __mul__(self, count: int):  # type: ignore[override]
            raise AssertionError("closer classification must not allocate marker * length")

    marker = Marker("`")

    assert not terminology_drift._is_exact_fence_closer("body\n", (marker, 131_072))
    assert terminology_drift._is_exact_fence_closer("```  \n", (marker, 3))


def test_long_unmatched_fence_has_bounded_line_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original_opener = terminology_drift._exact_fence_opener
    original_closer = terminology_drift._is_exact_fence_closer

    def counted_opener(line: str) -> tuple[str, int] | None:
        nonlocal calls
        calls += 1
        return original_opener(line)

    def counted_closer(line: str, opener: tuple[str, int]) -> bool:
        nonlocal calls
        calls += 1
        return original_closer(line, opener)

    monkeypatch.setattr(terminology_drift, "_exact_fence_opener", counted_opener)
    monkeypatch.setattr(terminology_drift, "_is_exact_fence_closer", counted_closer)
    marker = "`" * 131_072
    source = f"# Architecture\n\n{marker}\nworkspace host\n"

    assert terminology_drift.strip_markdown_code(source) == source
    assert calls == len(source.splitlines(keepends=True))
