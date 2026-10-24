from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOW = Path(".github/workflows/sarif-upload-example.yml")


def test_sarif_upload_example_has_required_security_events_permission() -> None:
    permissions = _job_mapping("scieqlint-sarif", "permissions")

    assert permissions == {
        "contents": "read",
        "security-events": "write",
    }


def test_sarif_upload_example_uses_cli_and_category() -> None:
    install_step = _job_step("scieqlint-sarif", "Install SciEqLint")
    run_step = _job_step("scieqlint-sarif", "Run SciEqLint SARIF")
    upload_step = _job_step("scieqlint-sarif", "Upload SARIF")
    quote = chr(34)

    assert install_step["run"] == "python -m pip install scieqlint==1.2.2"
    assert run_step["run"] == (
        f"set +e; scieqlint check {quote}docs/**/*.md{quote} "
        f"{quote}docs/**/*.ipynb{quote} "
        "--format sarif --output scieqlint.sarif; status=$?; "
        'test "$status" -le 1 || exit "$status"'
    )
    assert re.fullmatch(
        r"github/codeql-action/upload-sarif@[0-9a-f]{40}",
        upload_step["uses"],
    )
    assert upload_step["with"] == {
        "sarif_file": "scieqlint.sarif",
        "category": "scieqlint-docs",
    }


def test_sarif_upload_example_removes_stale_artifact() -> None:
    cleanup_step = _job_step("scieqlint-sarif", "Remove stale SARIF output")

    assert cleanup_step["run"] == "rm -f scieqlint.sarif"


def test_sarif_upload_example_requires_nonempty_json_output() -> None:
    verify_step = _job_step("scieqlint-sarif", "Verify SARIF output")

    assert verify_step["run"] == (
        "test -s scieqlint.sarif && python -m json.tool scieqlint.sarif >/dev/null"
    )


def test_sarif_artifact_checks_precede_upload() -> None:
    step_names = [step["name"] for step in _job_steps("scieqlint-sarif") if "name" in step]

    assert step_names.index("Remove stale SARIF output") < step_names.index("Run SciEqLint SARIF")
    assert step_names.index("Run SciEqLint SARIF") < step_names.index("Verify SARIF output")
    assert step_names.index("Verify SARIF output") < step_names.index("Upload SARIF")


@pytest.mark.parametrize(
    ("checker_status", "artifact_mode", "initial_artifact", "upload_eligible"),
    [
        pytest.param(0, "valid", None, True, id="clean-analysis"),
        pytest.param(1, "valid", None, True, id="findings"),
        pytest.param(2, "valid", None, False, id="operational-failure"),
        pytest.param(42, "valid", None, False, id="unexpected-failure"),
        pytest.param(0, "missing", None, False, id="clean-missing-output"),
        pytest.param(1, "missing", None, False, id="findings-missing-output"),
        pytest.param(0, "empty", None, False, id="clean-empty-output"),
        pytest.param(1, "empty", None, False, id="findings-empty-output"),
        pytest.param(0, "invalid", None, False, id="clean-invalid-json"),
        pytest.param(1, "invalid", None, False, id="findings-invalid-json"),
        pytest.param(
            1,
            "missing",
            '{"version": "2.1.0", "runs": []}',
            False,
            id="stale-output",
        ),
    ],
)
def test_sarif_upload_example_executes_status_and_artifact_contract(
    tmp_path: Path,
    checker_status: int,
    artifact_mode: str,
    initial_artifact: str | None,
    upload_eligible: bool,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_checker = fake_bin / "scieqlint"
    fake_checker.write_text(
        """#!/bin/sh
set -eu
case "$SCIEQLINT_ARTIFACT" in
    valid)
        printf '%s\\n' '{"version": "2.1.0", "runs": []}' > scieqlint.sarif
        ;;
    empty)
        : > scieqlint.sarif
        ;;
    invalid)
        printf '%s\\n' '{not-json' > scieqlint.sarif
        ;;
    missing)
        ;;
    *)
        exit 99
        ;;
esac
exit "$SCIEQLINT_STATUS"
""",
        encoding="utf-8",
    )
    fake_checker.chmod(0o755)

    artifact = tmp_path / "scieqlint.sarif"
    if initial_artifact is not None:
        artifact.write_text(initial_artifact, encoding="utf-8")

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
            "SCIEQLINT_ARTIFACT": artifact_mode,
            "SCIEQLINT_STATUS": str(checker_status),
        }
    )
    cleanup_command = _job_step("scieqlint-sarif", "Remove stale SARIF output")["run"]
    check_command = _job_step("scieqlint-sarif", "Run SciEqLint SARIF")["run"]
    verify_command = _job_step("scieqlint-sarif", "Verify SARIF output")["run"]

    cleanup_result = _run_workflow_step(cleanup_command, cwd=tmp_path, environment=environment)
    assert cleanup_result.returncode == 0, cleanup_result.stderr
    assert not artifact.exists()

    check_result = _run_workflow_step(check_command, cwd=tmp_path, environment=environment)
    if checker_status > 1:
        assert check_result.returncode == checker_status
        return

    assert check_result.returncode == 0, check_result.stderr
    verify_result = _run_workflow_step(verify_command, cwd=tmp_path, environment=environment)
    assert (verify_result.returncode == 0) is upload_eligible


def _run_workflow_step(
    command: str, *, cwd: Path, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", command],
        cwd=cwd,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )


def test_readme_code_scanning_example_uses_guarded_cli() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    section = readme.split("## Code scanning\n", 1)[1].split("## For contributors\n", 1)[0]

    assert (
        'run: set +e; scieqlint check "docs/**/*.md" --format sarif '
        '--output scieqlint.sarif; status=$?; test "$status" -le 1 || exit "$status"'
    ) in section
    assert (
        "run: test -s scieqlint.sarif && python -m json.tool scieqlint.sarif >/dev/null"
    ) in section


def _job(job_name: str) -> dict[str, Any]:
    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(workflow, dict)
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    job = jobs[job_name]
    assert isinstance(job, dict)
    return job


def _job_step(job_name: str, step_name: str) -> dict[str, Any]:
    for step in _job_steps(job_name):
        if step.get("name") == step_name:
            return step
    raise AssertionError(f"missing workflow step: {step_name}")


def _job_steps(job_name: str) -> list[dict[str, Any]]:
    steps = _job(job_name)["steps"]
    assert isinstance(steps, list)
    assert all(isinstance(step, dict) for step in steps)
    return steps


def _job_mapping(job_name: str, section_name: str) -> dict[str, Any]:
    mapping = _job(job_name)[section_name]
    assert isinstance(mapping, dict)
    return mapping
