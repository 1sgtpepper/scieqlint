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


def _staged_paths() -> tuple[str, ...]:
    # The index retains deleted and rename-source paths after pre-commit filters
    # them out of its candidate filename list.
    result = subprocess.run(
        [
            "git",
            "diff",
            "--cached",
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


def _candidate_paths(arguments: Sequence[str]) -> tuple[str, ...]:
    return tuple(argument for argument in arguments if argument != "--")


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the project check only for a supported pre-commit change."""
    args = tuple(sys.argv[1:] if arguments is None else arguments)
    paths = _candidate_paths(args)
    if not any(_is_supported(path) for path in paths):
        paths = _staged_paths()
    if not any(_is_supported(path) for path in paths):
        return 0
    return subprocess.run(
        [sys.executable, "-m", "scieqlint", "check", "--"],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
