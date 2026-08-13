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


def test_fences_remain_opaque_and_preserve_line_numbers() -> None:
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


@pytest.mark.parametrize(
    "source",
    [
        "````text\nworkspace host\n```\n",
        "~~~~~text\nfrontend host\n~~~~\n",
    ],
    ids=("backticks", "tildes"),
)
def test_shorter_same_character_closers_remain_unmatched(source: str) -> None:
    assert terminology_drift.strip_markdown_code(source) == source


def test_unmatched_opener_does_not_hide_later_complete_fence() -> None:
    source = "# Architecture\n\n````text\n```text\nworkspace host\n```\n"

    stripped = terminology_drift.strip_markdown_code(source)

    assert stripped.count("\n") == source.count("\n")
    assert "workspace host" not in stripped


def test_closed_outer_fence_does_not_consume_later_fence() -> None:
    source = "````text\n```text\ninside outer\n````\n```text\nlater workspace host\n```\n"

    stripped = terminology_drift.strip_markdown_code(source)

    assert stripped.count("\n") == source.count("\n")
    assert "inside outer" not in stripped
    assert "later workspace host" not in stripped


def test_longer_closer_is_opaque_without_widening_adjacent_syntax() -> None:
    unmatched = "# Architecture\n\n```text\nworkspace host\n"
    longer_closer = "```text\nworkspace host\n````  \t\nWorkspaceHost\n"
    indented = " ```text\nworkspace host\n ```\n"

    assert terminology_drift.strip_markdown_code(unmatched) == unmatched
    stripped = terminology_drift.strip_markdown_code(longer_closer)
    assert stripped.count("\n") == longer_closer.count("\n")
    assert "workspace host" not in stripped
    assert "WorkspaceHost" in stripped
    assert terminology_drift.strip_markdown_code(indented) == indented


@pytest.mark.parametrize(
    "closer",
    ["``\n", "~~~\n", "``` prose\n", "```\v\n"],
    ids=("short", "wrong-marker", "prose-after", "non-space-suffix"),
)
def test_invalid_closers_leave_the_fence_unmatched(closer: str) -> None:
    source = f"```text\nworkspace host\n{closer}"

    assert terminology_drift.strip_markdown_code(source) == source


def test_fence_successor_work_is_bounded_by_input_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opener_count = 2_000
    max_marker_length = 512
    source = "```x\n" * opener_count + "".join(
        f"{'`' * length}\n" for length in range(3, max_marker_length + 1)
    )
    candidate_calls = 0
    threshold_work = 0
    original_candidate = terminology_drift._fence_candidate
    original_range = range

    def counted_candidate(line: str) -> tuple[str, int, bool, bool] | None:
        nonlocal candidate_calls
        candidate_calls += 1
        return original_candidate(line)

    def counted_range(*args: int) -> range:
        nonlocal threshold_work
        values = original_range(*args)
        if len(args) == 2 and args[0] == 3:
            threshold_work += len(values)
        return values

    monkeypatch.setattr(terminology_drift, "_fence_candidate", counted_candidate)
    monkeypatch.setattr(terminology_drift, "range", counted_range, raising=False)

    terminology_drift.strip_markdown_code(source)

    assert candidate_calls == len(source.splitlines(keepends=True))
    assert threshold_work == sum(
        length - 2 for length in range(3, max_marker_length + 1)
    )
    assert threshold_work <= len(source)


@pytest.mark.parametrize(
    ("line", "opener", "expected"),
    [
        ("``\n", ("`", 4), False),
        ("```\n", ("`", 4), False),
        ("````\n", ("`", 4), True),
        ("````  \n", ("`", 4), True),
        ("`````\n", ("`", 4), True),
        ("~~~\n", ("`", 4), False),
        ("```text\n", ("`", 4), False),
        ("```\r\n", ("`", 4), False),
    ],
)
def test_fence_closer_predicate_enforces_marker_and_run_boundaries(
    line: str,
    opener: tuple[str, int],
    expected: bool,
) -> None:
    assert terminology_drift._is_fence_closer(line, opener) is expected


def test_closer_classification_does_not_rebuild_the_opener_marker() -> None:
    class Marker(str):
        def __mul__(self, count: int):  # type: ignore[override]
            raise AssertionError("closer classification must not allocate marker * length")

    marker = Marker("`")

    assert not terminology_drift._is_fence_closer("body\n", (marker, 131_072))
    assert terminology_drift._is_fence_closer("```  \n", (marker, 3))


def test_long_unmatched_fence_has_bounded_line_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original_candidate = terminology_drift._fence_candidate

    def counted_candidate(line: str) -> tuple[str, int, bool, bool] | None:
        nonlocal calls
        calls += 1
        return original_candidate(line)

    monkeypatch.setattr(terminology_drift, "_fence_candidate", counted_candidate)
    marker = "`" * 131_072
    source = f"# Architecture\n\n{marker}\nworkspace host\n"

    assert terminology_drift.strip_markdown_code(source) == source
    assert calls == len(source.splitlines(keepends=True))
