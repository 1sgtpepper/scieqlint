"""Pre-commit adapter for complete project-context checks."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from scieqlint.io.discover import SUPPORTED_SUFFIXES


def _is_supported(path: str) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_SUFFIXES


def _diff_records(*diff_arguments: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    result = subprocess.run(
        [
            "git",
            "diff",
            *diff_arguments,
            "--name-status",
            "--diff-filter=ACDMRTUXB",
            "-z",
            "--",
        ],
        check=True,
        capture_output=True,
    )
    fields = result.stdout.split(b"\0")
    records: list[tuple[str, tuple[str, ...]]] = []
    index = 0
    while index < len(fields) - 1:
        status = os.fsdecode(fields[index])
        index += 1
        path_count = 2 if status[:1] in {"R", "C"} else 1
        paths = tuple(os.fsdecode(path) for path in fields[index : index + path_count])
        index += path_count
        records.append((status[:1], paths))
    return tuple(records)


def _staged_records() -> tuple[tuple[str, tuple[str, ...]], ...]:
    return _diff_records("--cached")


def _invisible_paths(
    records: Sequence[tuple[str, tuple[str, ...]]],
    candidate_paths: Sequence[str] = (),
    staged_paths: set[str] | None = None,
) -> tuple[str, ...]:
    # Recover only paths pre-commit removes before invocation: deletions and
    # rename sources. Existing additions and modifications remain candidate-owned.
    candidates = set(candidate_paths)
    staged = set() if staged_paths is None else staged_paths
    paths: list[str] = []
    for status, changed_paths in records:
        if status == "D" and (not candidates or candidates <= staged):
            paths.extend(changed_paths)
        elif status == "R" and (not candidates or changed_paths[1] in candidates):
            paths.append(changed_paths[0])
    return tuple(paths)


def _split_arguments(arguments: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    args = tuple(arguments)
    if not args:
        return (), ()
    try:
        boundary = args.index("--")
    except ValueError as error:
        raise ValueError(
            "SciEqLint pre-commit hook arguments must include '--' between check "
            "options and filenames; preserve it when overriding hook args"
        ) from error
    return args[:boundary], args[boundary + 1 :]


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the project check only for a supported pre-commit change."""
    args = tuple(sys.argv[1:] if arguments is None else arguments)
    if os.environ.get("PRE_COMMIT_FROM_REF") or os.environ.get("PRE_COMMIT_TO_REF"):
        sys.stderr.write(
            "SciEqLint pre-commit hook supports ordinary staged runs only; "
            "revision-range runs are not supported\n"
        )
        return 2
    try:
        check_args, candidate_paths = _split_arguments(args)
    except ValueError as error:
        sys.stderr.write(f"{error}\n")
        return 2

    if any(_is_supported(path) for path in candidate_paths):
        paths = candidate_paths
    else:
        staged_records = _staged_records()
        staged_paths = {path for _, changed_paths in staged_records for path in changed_paths}
        paths = (
            *candidate_paths,
            *_invisible_paths(
                staged_records,
                candidate_paths,
                staged_paths,
            ),
        )
    if not any(_is_supported(path) for path in paths):
        return 0
    return subprocess.run(
        [sys.executable, "-m", "scieqlint", "check", *check_args, "--"],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
