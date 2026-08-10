from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[1]
REPLAY_COMMAND = REPOSITORY_ROOT / "tools" / "public_regression_replay.py"
NODE_ID = "tests/test_behavior.py::test_public_behavior[new-value]"
SECOND_NODE_ID = "tests/test_behavior.py::test_second_public_behavior"
MARKER = (
    "public_regression: new public bug regression that must fail by a test-owned assertion "
    "on the pull request base"
)
UNMARKED_TEST = """import demo
import pytest

@pytest.mark.parametrize("expected", ["new"], ids=["new-value"])
def test_public_behavior(expected: str) -> None:
    assert demo.VALUE == expected
"""
MARKED_TEST = """import demo
import pytest

@pytest.mark.public_regression
@pytest.mark.parametrize("expected", ["new"], ids=["new-value"])
def test_public_behavior(expected: str) -> None:
    assert demo.VALUE == expected
"""
MULTIPLE_MARKED_TEST = (
    MARKED_TEST
    + """

@pytest.mark.public_regression
def test_second_public_behavior() -> None:
    assert demo.SECOND == "new"
"""
)
SETUP_MARKED_TEST = """import demo
import pytest

@pytest.fixture
def actual_value():
    return demo.VALUE

@pytest.mark.public_regression
@pytest.mark.parametrize("expected", ["new"], ids=["new-value"])
def test_public_behavior(expected: str, actual_value: str) -> None:
    assert actual_value == expected
"""
TEARDOWN_MARKED_TEST = """import demo
import pytest

@pytest.fixture
def cleanup():
    yield
    demo.finish()

@pytest.mark.public_regression
@pytest.mark.parametrize("expected", ["new"], ids=["new-value"])
def test_public_behavior(expected: str, cleanup) -> None:
    assert demo.VALUE == expected
"""
PYTEST_FAIL_MARKED_TEST = """import demo
import pytest

@pytest.mark.public_regression
@pytest.mark.parametrize("expected", ["new"], ids=["new-value"])
def test_public_behavior(expected: str) -> None:
    if demo.VALUE != expected:
        pytest.fail("public behavior mismatch")
"""
HELPER_ASSERTION_MARKED_TEST = """import demo
import pytest

def _assert_public_value(expected: str) -> None:
    assert demo.VALUE == expected

@pytest.mark.public_regression
@pytest.mark.parametrize("expected", ["new"], ids=["new-value"])
def test_public_behavior(expected: str) -> None:
    _assert_public_value(expected)
"""
HELPER_PYTEST_FAIL_MARKED_TEST = """import demo
import pytest

def _require_public_value(expected: str) -> None:
    if demo.VALUE != expected:
        pytest.fail("public behavior mismatch")

@pytest.mark.public_regression
@pytest.mark.parametrize("expected", ["new"], ids=["new-value"])
def test_public_behavior(expected: str) -> None:
    _require_public_value(expected)
"""
CALL_MARKED_TEST = """import demo
import pytest

@pytest.mark.public_regression
@pytest.mark.parametrize("expected", ["new"], ids=["new-value"])
def test_public_behavior(expected: str) -> None:
    assert demo.current_value() == expected
"""
XFAIL_MARKED_TEST = """import demo
import pytest

@pytest.mark.public_regression
@pytest.mark.xfail
@pytest.mark.parametrize("expected", ["new"], ids=["new-value"])
def test_public_behavior(expected: str) -> None:
    assert demo.VALUE == expected
"""
SKIP_MARKED_TEST = """import demo
import pytest

@pytest.mark.public_regression
@pytest.mark.skip(reason="not enforcing")
@pytest.mark.parametrize("expected", ["new"], ids=["new-value"])
def test_public_behavior(expected: str) -> None:
    assert demo.VALUE == expected
"""
TEARDOWN_SKIP_MARKED_TEST = """import demo
import pytest

@pytest.fixture
def cleanup():
    yield
    pytest.skip("teardown deliberately skipped")

@pytest.mark.public_regression
@pytest.mark.parametrize("expected", ["new"], ids=["new-value"])
def test_public_behavior(expected: str, cleanup) -> None:
    assert demo.VALUE == expected
"""
TEARDOWN_XFAIL_MARKED_TEST = """import demo
import pytest

@pytest.fixture
def cleanup():
    yield
    pytest.xfail("teardown deliberately xfailed")

@pytest.mark.public_regression
@pytest.mark.parametrize("expected", ["new"], ids=["new-value"])
def test_public_behavior(expected: str, cleanup) -> None:
    assert demo.VALUE == expected
"""
CONTROL_TEST = """

def test_normative_control() -> None:
    assert True
"""
BROKEN_COLLECTION_TEST = 'raise RuntimeError("collection failed")\n'


def test_replay_accepts_base_mismatch_and_head_pass(tmp_path: Path) -> None:
    base, head = _write_revisions(tmp_path, base_module='VALUE = "old"\n')

    result = _run_replay(base, head)

    assert result.returncode == 0, result.stdout
    assert result.stdout.splitlines() == [f"HEAD PASS {NODE_ID}", f"BASE MISMATCH {NODE_ID}"]


def test_replay_accepts_pytest_fail_as_behavioral_mismatch(tmp_path: Path) -> None:
    base, head = _write_revisions(
        tmp_path,
        base_module='VALUE = "old"\n',
        head_test=PYTEST_FAIL_MARKED_TEST,
    )

    result = _run_replay(base, head)

    assert result.returncode == 0, result.stdout
    assert result.stdout.splitlines() == [f"HEAD PASS {NODE_ID}", f"BASE MISMATCH {NODE_ID}"]


def test_replay_accepts_assertion_from_private_test_helper(tmp_path: Path) -> None:
    base, head = _write_revisions(
        tmp_path,
        base_module='VALUE = "old"\n',
        head_test=HELPER_ASSERTION_MARKED_TEST,
    )

    result = _run_replay(base, head)

    assert result.returncode == 0, result.stdout
    assert result.stdout.splitlines() == [f"HEAD PASS {NODE_ID}", f"BASE MISMATCH {NODE_ID}"]


def test_replay_accepts_pytest_fail_from_private_test_helper(tmp_path: Path) -> None:
    base, head = _write_revisions(
        tmp_path,
        base_module='VALUE = "old"\n',
        head_test=HELPER_PYTEST_FAIL_MARKED_TEST,
    )

    result = _run_replay(base, head)

    assert result.returncode == 0, result.stdout
    assert result.stdout.splitlines() == [f"HEAD PASS {NODE_ID}", f"BASE MISMATCH {NODE_ID}"]


def test_replay_rejects_node_that_passes_both_revisions(tmp_path: Path) -> None:
    base, head = _write_revisions(tmp_path, base_module='VALUE = "new"\n')

    result = _run_replay(base, head)

    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        f"HEAD PASS {NODE_ID}",
        f"BASE PASS {NODE_ID}: rejected because the regression also passes on base",
    ]


def test_replay_rejects_head_assertion_failure(tmp_path: Path) -> None:
    base, head = _write_revisions(
        tmp_path,
        base_module='VALUE = "old"\n',
        head_module='VALUE = "old"\n',
    )

    result = _run_replay(base, head)

    assert result.returncode == 1
    assert result.stdout.splitlines() == [f"HEAD MISMATCH {NODE_ID}"]


def test_replay_rejects_expected_failure_marker(tmp_path: Path) -> None:
    base, head = _write_revisions(
        tmp_path,
        base_module='VALUE = "old"\n',
        head_test=XFAIL_MARKED_TEST,
    )

    result = _run_replay(base, head)

    assert result.returncode == 1
    assert result.stdout.splitlines()[0] == f"HEAD API INCOMPATIBLE {NODE_ID}"
    assert "xpassed" in result.stdout.lower()


def test_replay_rejects_skipped_marker(tmp_path: Path) -> None:
    base, head = _write_revisions(
        tmp_path,
        base_module='VALUE = "old"\n',
        head_test=SKIP_MARKED_TEST,
    )

    result = _run_replay(base, head)

    assert result.returncode == 1
    assert result.stdout.splitlines()[0] == f"HEAD API INCOMPATIBLE {NODE_ID}"
    assert "skipped" in result.stdout.lower()


def test_replay_reports_head_api_incompatibility(tmp_path: Path) -> None:
    base, head = _write_revisions(
        tmp_path,
        base_module='VALUE = "old"\n',
        head_module="OTHER = 1\n",
    )

    result = _run_replay(base, head)

    assert result.returncode == 1
    assert result.stdout.splitlines()[0] == f"HEAD API INCOMPATIBLE {NODE_ID}"
    assert "AttributeError" in result.stdout


def test_replay_reports_base_call_api_incompatibility(tmp_path: Path) -> None:
    base, head = _write_revisions(tmp_path, base_module="OTHER = 1\n")

    result = _run_replay(base, head)

    assert result.returncode == 1
    assert result.stdout.splitlines()[:2] == [
        f"HEAD PASS {NODE_ID}",
        f"BASE API INCOMPATIBLE {NODE_ID}",
    ]
    assert "AttributeError" in result.stdout


def test_replay_rejects_assertion_from_base_package(tmp_path: Path) -> None:
    base, head = _write_revisions(
        tmp_path,
        base_module=(
            "def current_value():\n"
            '    raise AssertionError("internal invariant failed before the oracle")\n'
        ),
        head_module='def current_value():\n    return "new"\n',
        head_test=CALL_MARKED_TEST,
    )

    result = _run_replay(base, head)

    assert result.returncode == 1
    assert result.stdout.splitlines()[:2] == [
        f"HEAD PASS {NODE_ID}",
        f"BASE API INCOMPATIBLE {NODE_ID}",
    ]
    assert "internal invariant failed before the oracle" in result.stdout


def test_replay_rejects_pytest_fail_from_base_package(tmp_path: Path) -> None:
    base, head = _write_revisions(
        tmp_path,
        base_module=(
            "import pytest\n\n"
            "def current_value():\n"
            '    pytest.fail("internal failure before the oracle")\n'
        ),
        head_module='def current_value():\n    return "new"\n',
        head_test=CALL_MARKED_TEST,
    )

    result = _run_replay(base, head)

    assert result.returncode == 1
    assert result.stdout.splitlines()[:2] == [
        f"HEAD PASS {NODE_ID}",
        f"BASE API INCOMPATIBLE {NODE_ID}",
    ]
    assert "internal failure before the oracle" in result.stdout


def test_replay_reports_base_setup_api_incompatibility(tmp_path: Path) -> None:
    base, head = _write_revisions(
        tmp_path,
        base_module="OTHER = 1\n",
        head_test=SETUP_MARKED_TEST,
    )

    result = _run_replay(base, head)

    assert result.returncode == 1
    assert result.stdout.splitlines()[:2] == [
        f"HEAD PASS {NODE_ID}",
        f"BASE API INCOMPATIBLE {NODE_ID}",
    ]
    assert "AttributeError" in result.stdout


def test_replay_reports_base_teardown_api_incompatibility(tmp_path: Path) -> None:
    base, head = _write_revisions(
        tmp_path,
        base_module='VALUE = "old"\n',
        head_module='VALUE = "new"\n\ndef finish():\n    pass\n',
        head_test=TEARDOWN_MARKED_TEST,
    )

    result = _run_replay(base, head)

    assert result.returncode == 1
    assert result.stdout.splitlines()[:2] == [
        f"HEAD PASS {NODE_ID}",
        f"BASE API INCOMPATIBLE {NODE_ID}",
    ]
    assert "AttributeError" in result.stdout


def test_replay_rejects_skipped_teardown(tmp_path: Path) -> None:
    base, head = _write_revisions(
        tmp_path,
        base_module='VALUE = "old"\n',
        head_test=TEARDOWN_SKIP_MARKED_TEST,
    )

    result = _run_replay(base, head)

    assert result.returncode == 1
    assert result.stdout.splitlines()[0] == f"HEAD API INCOMPATIBLE {NODE_ID}"
    assert "skipped" in result.stdout.lower()


def test_replay_rejects_xfailed_teardown(tmp_path: Path) -> None:
    base, head = _write_revisions(
        tmp_path,
        base_module='VALUE = "old"\n',
        head_test=TEARDOWN_XFAIL_MARKED_TEST,
    )

    result = _run_replay(base, head)

    assert result.returncode == 1
    assert result.stdout.splitlines()[0] == f"HEAD API INCOMPATIBLE {NODE_ID}"
    assert "xfailed" in result.stdout.lower()


def test_replay_continues_after_rejected_node(tmp_path: Path) -> None:
    base, head = _write_revisions(
        tmp_path,
        base_module='VALUE = "new"\nSECOND = "old"\n',
        head_module='VALUE = "new"\nSECOND = "new"\n',
        head_test=MULTIPLE_MARKED_TEST,
    )

    result = _run_replay(base, head)

    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        f"HEAD PASS {NODE_ID}",
        f"BASE PASS {NODE_ID}: rejected because the regression also passes on base",
        f"HEAD PASS {SECOND_NODE_ID}",
        f"BASE MISMATCH {SECOND_NODE_ID}",
    ]


def test_replay_ignores_existing_and_unmarked_nodes(tmp_path: Path) -> None:
    base, head = _write_revisions(
        tmp_path,
        base_module='VALUE = "old"\n',
        base_test=MARKED_TEST,
    )

    result = _run_replay(base, head)

    assert result.returncode == 0, result.stdout
    assert result.stdout == "No newly added public regressions.\n"


def test_replay_skips_base_collection_without_head_markers(tmp_path: Path) -> None:
    base, head = _write_revisions(
        tmp_path,
        base_module='VALUE = "old"\n',
        base_test=BROKEN_COLLECTION_TEST,
        head_test=UNMARKED_TEST + CONTROL_TEST,
    )

    result = _run_replay(base, head)

    assert result.returncode == 0, result.stdout
    assert result.stdout == "No newly added public regressions.\n"


def test_replay_rejects_invalid_base_checkout_with_role(tmp_path: Path) -> None:
    _, head = _write_revisions(tmp_path, base_module='VALUE = "old"\n')
    missing_base = tmp_path / "missing-base"

    result = _run_replay(missing_base, head)

    assert result.returncode == 2
    assert result.stdout == ""
    assert f"base checkout must contain src/ and tests/: {missing_base}" in result.stderr


def test_replay_internal_modes_require_role_arguments(tmp_path: Path) -> None:
    config = tmp_path / "pytest.ini"
    config.write_text("[pytest]\n", encoding="utf-8")
    common = ["--root", str(tmp_path), "--config", str(config)]

    collect = subprocess.run(
        [sys.executable, str(REPLAY_COMMAND), "_collect", *common],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    run = subprocess.run(
        [sys.executable, str(REPLAY_COMMAND), "_run", *common],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert collect.returncode == 2
    assert "_collect requires --output" in collect.stderr
    assert run.returncode == 2
    assert "_run requires --selector" in run.stderr


def test_replay_reports_base_collection_failure_for_exact_head_node(tmp_path: Path) -> None:
    base, head = _write_revisions(
        tmp_path,
        base_module='VALUE = "old"\n',
        base_test=BROKEN_COLLECTION_TEST,
    )

    result = _run_replay(base, head)

    assert result.returncode == 1
    assert result.stdout.splitlines()[0] == (
        f"BASE API INCOMPATIBLE {NODE_ID}: marker collection failed"
    )
    assert "collection failed" in result.stdout


def test_replay_reports_head_collection_failure(tmp_path: Path) -> None:
    base, head = _write_revisions(
        tmp_path,
        base_module='VALUE = "old"\n',
        head_test=BROKEN_COLLECTION_TEST,
    )

    result = _run_replay(base, head)

    assert result.returncode == 1
    assert result.stdout.splitlines()[0] == "HEAD API INCOMPATIBLE: marker collection failed"
    assert "collection failed" in result.stdout


def test_replay_marker_command_and_pull_request_job_are_wired() -> None:
    config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    pytest_options = config["tool"]["pytest"]["ini_options"]
    sdist_include = config["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert pytest_options["markers"] == [MARKER]
    assert "tools/public_regression_replay.py" in sdist_include
    assert "  public-regression-replay:\n" in workflow
    assert "    if: github.event_name == 'pull_request'\n" in workflow
    assert "          ref: ${{ github.event.pull_request.base.sha }}\n" in workflow
    assert "        run: python tools/public_regression_replay.py --base .base\n" in workflow


def _write_revisions(
    tmp_path: Path,
    *,
    base_module: str,
    head_module: str = 'VALUE = "new"\n',
    base_test: str = UNMARKED_TEST,
    head_test: str = MARKED_TEST + CONTROL_TEST,
) -> tuple[Path, Path]:
    base = tmp_path / "base"
    head = tmp_path / "head"
    _write_revision(
        base,
        module=base_module,
        test_source=base_test,
    )
    _write_revision(
        head,
        module=head_module,
        test_source=head_test,
    )
    return base, head


def _write_revision(
    root: Path,
    *,
    module: str,
    test_source: str,
) -> None:
    package = root / "src" / "demo"
    tests = root / "tests"
    package.mkdir(parents=True)
    tests.mkdir()
    (package / "__init__.py").write_text(module, encoding="utf-8")
    (tests / "test_behavior.py").write_text(test_source, encoding="utf-8")


def _run_replay(base: Path, head: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("PYTEST_ADDOPTS", None)
    return subprocess.run(
        [
            sys.executable,
            str(REPLAY_COMMAND),
            "--base",
            str(base),
            "--head",
            str(head),
        ],
        cwd=head,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )
