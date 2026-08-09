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


def _split_arguments(arguments: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    args = tuple(arguments)
    if not args:
        return (), ()
    try:
        boundary = args.index("--")
    except ValueError as error:
        raise ValueError(
            "SciEqLint pre-commit hook arguments must include '--' after check "
            "options; preserve it when overriding hook args"
        ) from error
    return args[:boundary], args[boundary + 1 :]


def main(arguments: Sequence[str] | None = None) -> int:
    """Run one project check for a supported staged change."""
    args = tuple(sys.argv[1:] if arguments is None else arguments)
    if os.environ.get("PRE_COMMIT_FROM_REF") or os.environ.get("PRE_COMMIT_TO_REF"):
        sys.stderr.write(
            "SciEqLint pre-commit hook supports ordinary staged runs only; "
            "revision-range runs are not supported\n"
        )
        return 2
    try:
        check_args, configured_paths = _split_arguments(args)
    except ValueError as error:
        sys.stderr.write(f"{error}\n")
        return 2

    if configured_paths:
        sys.stderr.write(
            "SciEqLint pre-commit hook does not accept filenames after '--'; "
            "use checker options before the boundary\n"
        )
        return 2

    staged_records = _staged_records()
    if not any(
        _is_supported(path) for _, changed_paths in staged_records for path in changed_paths
    ):
        return 0
    return subprocess.run(
        [sys.executable, "-m", "scieqlint", "check", *check_args, "--"],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
