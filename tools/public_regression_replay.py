"""Require new public regressions to fail by a test-owned assertion on base."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from enum import Enum
from pathlib import Path

import pytest

MARKER = "public_regression"
MARKER_DESCRIPTION = (
    "new public bug regression that must fail by a test-owned assertion on the pull request base"
)
_PASS = 0
_MISMATCH = 10
_INCOMPATIBLE = 11


class _CollectionError(RuntimeError):
    """A revision's pytest marker inventory could not be collected."""


class _MarkedNodeCollector:
    def __init__(self) -> None:
        self.node_ids: tuple[str, ...] = ()

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        self.node_ids = tuple(
            item.nodeid for item in session.items if item.get_closest_marker(MARKER) is not None
        )


class _CaseStatus(Enum):
    UNSEEN = "unseen"
    PASS = "pass"
    MISMATCH = "mismatch"
    INCOMPATIBLE = "incompatible"


class _CaseOutcome:
    def __init__(self) -> None:
        self.status = _CaseStatus.UNSEEN

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo[None]):
        outcome = yield
        report = outcome.get_result()
        if self.status is _CaseStatus.INCOMPATIBLE:
            return
        if report.when != "call":
            if not report.passed:
                self.status = _CaseStatus.INCOMPATIBLE
            return

        assertion_failure = (
            report.failed
            and call.excinfo is not None
            and call.excinfo.errisinstance((AssertionError, pytest.fail.Exception))
        )
        failure_origin = (
            getattr(getattr(report.longrepr, "reprcrash", None), "path", None)
            if assertion_failure
            else None
        )
        failure_path = Path(failure_origin) if failure_origin is not None else None
        if failure_path is not None and not failure_path.is_absolute():
            failure_path = item.config.rootpath / failure_path
        test_root = (item.config.rootpath / "tests").resolve()

        if report.passed and not hasattr(report, "wasxfail"):
            self.status = _CaseStatus.PASS
        elif assertion_failure and (
            failure_path is not None and failure_path.resolve().is_relative_to(test_root)
        ):
            self.status = _CaseStatus.MISMATCH
        else:
            self.status = _CaseStatus.INCOMPATIBLE

    def exit_code(self, pytest_exit_code: int) -> int:
        if self.status is _CaseStatus.PASS and pytest_exit_code == 0:
            return _PASS
        if self.status is _CaseStatus.MISMATCH and pytest_exit_code == 1:
            return _MISMATCH
        return _INCOMPATIBLE


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in {"_collect", "_run"}:
        return _internal_main(arguments)

    parser = argparse.ArgumentParser(
        description=(
            "Replay newly marked public regressions against head and base package sources. "
            "Exit status is zero only when every new node passes on head and fails by "
            "a test-owned assertion on base."
        )
    )
    parser.add_argument(
        "--base",
        type=Path,
        required=True,
        help="Checkout of the exact pull-request base revision.",
    )
    parser.add_argument(
        "--head",
        type=Path,
        default=Path("."),
        help="Checkout containing the proposed tests and package source. Defaults to '.'.",
    )
    args = parser.parse_args(arguments)
    head = args.head.resolve()
    base = args.base.resolve()
    for role, root in (("head", head), ("base", base)):
        if not (root / "src").is_dir() or not (root / "tests").is_dir():
            parser.error(f"{role} checkout must contain src/ and tests/: {root}")

    with tempfile.TemporaryDirectory(prefix="public-regression-replay-") as temporary:
        temporary_path = Path(temporary)
        config = temporary_path / "pytest.ini"
        config.write_text(
            "[pytest]\n"
            "addopts = --strict-markers --strict-config\n"
            "markers =\n"
            f"    {MARKER}: {MARKER_DESCRIPTION}\n",
            encoding="utf-8",
        )

        try:
            head_nodes = _collect_nodes(
                test_root=head,
                package_src=head / "src",
                config=config,
                output=temporary_path / "head-nodes.txt",
            )
        except _CollectionError as exc:
            _write_line("HEAD API INCOMPATIBLE: marker collection failed")
            _write_details(str(exc))
            return 1

        if not head_nodes:
            _write_line("No newly added public regressions.")
            return 0

        try:
            base_nodes = _collect_nodes(
                test_root=base,
                package_src=base / "src",
                config=config,
                output=temporary_path / "base-nodes.txt",
            )
        except _CollectionError as exc:
            for node_id in head_nodes:
                _write_line(f"BASE API INCOMPATIBLE {node_id}: marker collection failed")
            _write_details(str(exc))
            return 1

        base_node_set = set(base_nodes)
        new_nodes = tuple(node_id for node_id in head_nodes if node_id not in base_node_set)
        if not new_nodes:
            _write_line("No newly added public regressions.")
            return 0

        return _replay_nodes(new_nodes, head=head, base=base, config=config)


def _collect_nodes(
    *,
    test_root: Path,
    package_src: Path,
    config: Path,
    output: Path,
) -> tuple[str, ...]:
    result = _invoke_internal(
        "_collect",
        test_root=test_root,
        package_src=package_src,
        config=config,
        output=output,
    )
    if result.returncode != 0:
        raise _CollectionError(_combined_output(result))
    return tuple(line for line in output.read_text(encoding="utf-8").splitlines() if line)


def _replay_nodes(nodes: tuple[str, ...], *, head: Path, base: Path, config: Path) -> int:
    rejected = False
    for node_id in nodes:
        head_result = _invoke_internal(
            "_run",
            test_root=head,
            package_src=head / "src",
            config=config,
            selector=node_id,
        )
        if head_result.returncode == _PASS:
            _write_line(f"HEAD PASS {node_id}")
        elif head_result.returncode == _MISMATCH:
            _write_line(f"HEAD MISMATCH {node_id}")
            rejected = True
            continue
        else:
            _write_line(f"HEAD API INCOMPATIBLE {node_id}")
            _write_details(_combined_output(head_result))
            rejected = True
            continue

        base_result = _invoke_internal(
            "_run",
            test_root=head,
            package_src=base / "src",
            config=config,
            selector=node_id,
        )
        if base_result.returncode == _MISMATCH:
            _write_line(f"BASE MISMATCH {node_id}")
        elif base_result.returncode == _PASS:
            _write_line(f"BASE PASS {node_id}: rejected because the regression also passes on base")
            rejected = True
        else:
            _write_line(f"BASE API INCOMPATIBLE {node_id}")
            _write_details(_combined_output(base_result))
            rejected = True
    return 1 if rejected else 0


def _invoke_internal(
    mode: str,
    *,
    test_root: Path,
    package_src: Path,
    config: Path,
    output: Path | None = None,
    selector: str | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        mode,
        "--root",
        str(test_root),
        "--config",
        str(config),
    ]
    if output is not None:
        command.extend(("--output", str(output)))
    if selector is not None:
        command.extend(("--selector", selector))

    environment = os.environ.copy()
    environment.pop("PYTEST_ADDOPTS", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join((str(package_src), str(test_root)))
    return subprocess.run(
        command,
        cwd=test_root,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )


def _internal_main(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("mode", choices=("_collect", "_run"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selector")
    args = parser.parse_args(arguments)
    root = args.root.resolve()

    if args.mode == "_collect":
        if args.output is None:
            parser.error("_collect requires --output")
        collector = _MarkedNodeCollector()
        exit_code = int(
            pytest.main(
                [
                    "-c",
                    str(args.config),
                    f"--rootdir={root}",
                    "--collect-only",
                    "-q",
                    str(root / "tests"),
                ],
                plugins=[collector],
            )
        )
        if exit_code != 0:
            return _INCOMPATIBLE
        args.output.write_text(
            "".join(f"{node_id}\n" for node_id in collector.node_ids),
            encoding="utf-8",
        )
        return _PASS

    if args.selector is None:
        parser.error("_run requires --selector")
    outcome = _CaseOutcome()
    exit_code = int(
        pytest.main(
            [
                "-c",
                str(args.config),
                f"--rootdir={root}",
                "-q",
                args.selector,
            ],
            plugins=[outcome],
        )
    )
    return outcome.exit_code(exit_code)


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())


def _write_line(value: str) -> None:
    sys.stdout.write(f"{value}\n")


def _write_details(value: str) -> None:
    for line in value.splitlines():
        sys.stdout.write(f"  {line}\n")


if __name__ == "__main__":
    raise SystemExit(main())
