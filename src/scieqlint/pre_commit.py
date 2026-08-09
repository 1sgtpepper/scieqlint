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


def _diff_paths(*diff_arguments: str) -> tuple[str, ...]:
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
    paths: list[str] = []
    index = 0
    while index < len(fields) - 1:
        status = os.fsdecode(fields[index])
        index += 1
        path_count = 2 if status[:1] in {"R", "C"} else 1
        paths.extend(os.fsdecode(path) for path in fields[index : index + path_count])
        index += path_count
    return tuple(paths)


def _staged_paths() -> tuple[str, ...]:
    # The index retains deleted and rename-source paths after pre-commit filters
    # them out of its candidate filename list.
    return _diff_paths("--cached")


def _range_paths(from_ref: str, to_ref: str) -> tuple[str, ...]:
    try:
        return _diff_paths(f"{from_ref}...{to_ref}")
    except subprocess.CalledProcessError:
        return _diff_paths(f"{from_ref}..{to_ref}")


def _range_refs() -> tuple[str, str] | None:
    from_ref = os.environ.get("PRE_COMMIT_FROM_REF")
    to_ref = os.environ.get("PRE_COMMIT_TO_REF")
    if from_ref is None and to_ref is None:
        return None
    if not from_ref or not to_ref:
        raise ValueError(
            "SciEqLint pre-commit hook requires both PRE_COMMIT_FROM_REF and "
            "PRE_COMMIT_TO_REF"
        )
    return from_ref, to_ref


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
    try:
        check_args, candidate_paths = _split_arguments(args)
        refs = _range_refs()
    except ValueError as error:
        sys.stderr.write(f"{error}\n")
        return 2

    if refs is not None:
        paths = _range_paths(*refs)
    elif candidate_paths:
        paths = candidate_paths
    else:
        paths = _staged_paths()
    if not any(_is_supported(path) for path in paths):
        return 0
    return subprocess.run(
        [sys.executable, "-m", "scieqlint", "check", *check_args, "--"],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
