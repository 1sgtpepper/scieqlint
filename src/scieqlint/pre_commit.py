"""Pre-commit adapter for complete project-context checks."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence


def _split_arguments(arguments: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    args = tuple(arguments)
    try:
        boundary = args.index("--")
    except ValueError as error:
        raise ValueError(
            "SciEqLint pre-commit hook arguments must include '--' after check "
            "options; preserve it when overriding hook args"
        ) from error
    return args[:boundary], args[boundary + 1 :]


def main(arguments: Sequence[str] | None = None) -> int:
    """Run one complete project check for an ordinary pre-commit invocation."""
    args = tuple(sys.argv[1:] if arguments is None else arguments)
    if os.environ.get("PRE_COMMIT_FROM_REF") or os.environ.get("PRE_COMMIT_TO_REF"):
        sys.stderr.write(
            "SciEqLint pre-commit hook supports ordinary pre-commit runs only; "
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

    return subprocess.run(
        [sys.executable, "-m", "scieqlint", "check", *check_args, "--"],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
