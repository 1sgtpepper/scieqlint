from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml


def _parse_workflow(text: str) -> dict[str, Any]:
    workflow = yaml.load(text, Loader=yaml.BaseLoader)
    assert isinstance(workflow, dict)
    return workflow


def _workflow(path: Path) -> dict[str, Any]:
    return _parse_workflow(path.read_text(encoding="utf-8"))


def _workflow_job(workflow: dict[str, Any], name: str) -> dict[str, Any]:
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    job = jobs[name]
    assert isinstance(job, dict)
    return job


def _workflow_step(
    job: dict[str, Any],
    *,
    name: str | None = None,
    step_id: str | None = None,
    uses: str | None = None,
) -> dict[str, Any]:
    steps = job["steps"]
    assert isinstance(steps, list)
    for step in steps:
        if not isinstance(step, dict):
            continue
        if name is not None and step.get("name") != name:
            continue
        if step_id is not None and step.get("id") != step_id:
            continue
        if uses is not None and step.get("uses") != uses:
            continue
        return step
    raise AssertionError(f"workflow step not found: {name or step_id or uses}")


def _step_run(step: dict[str, Any]) -> str:
    run = step["run"]
    assert isinstance(run, str)
    return run


def _normalized_shell_commands(run: str) -> list[str]:
    commands: list[str] = []
    pending = ""
    for raw_line in run.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        continuation = line.endswith("\\")
        fragment = line[:-1].rstrip() if continuation else line
        pending = f"{pending} {fragment}".strip()
        if not continuation:
            commands.append(pending)
            pending = ""
    if pending:
        commands.append(pending)
    return commands


def test_release_version_metadata_is_consistent() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    init_tree = ast.parse(Path("src/scieqlint/__init__.py").read_text(encoding="utf-8"))
    citation = Path("CITATION.cff").read_text(encoding="utf-8")

    assert project["version"] == "1.1.0"
    assert _assigned_string(init_tree, "__version__") == project["version"]
    assert f"version: {project['version']}" in citation


def test_implementation_status_uses_the_current_release_version() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]

    for path in (
        Path("IMPLEMENTATION_STATUS.md"),
        Path("PACK_MANIFEST.md"),
        Path("SPEC.md"),
    ):
        text = path.read_text(encoding="utf-8")
        assert f"v{project['version']}" in text, path
        assert "v0.1.5 analyzer" not in text, path


def test_release_readiness_documents_agree_on_independent_evidence_count() -> None:
    corpus = json.loads(Path("benchmarks/accuracy/corpus-v1.json").read_text(encoding="utf-8"))
    equation_ids = {
        case["independent_equation_id"] for case in corpus["cases"] if not case["synthetic"]
    }
    for path in (
        Path("docs/releases/v1.0.0-contract-readiness.md"),
        Path("docs/releases/v1.0.0-stabilization-checklist.md"),
    ):
        match = re.search(
            r"corpus (?:provides|contains) (\d+) source equations",
            path.read_text(encoding="utf-8"),
        )
        assert match is not None, path
        assert int(match.group(1)) == len(equation_ids), path


def test_current_release_remains_pre_alpha() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert "Development Status :: 2 - Pre-Alpha" in project["classifiers"]
    assert not any("Production/Stable" in classifier for classifier in project["classifiers"])


def test_documentation_url_points_to_current_repository_docs() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["urls"]["Documentation"] == (
        "https://github.com/1sgtpepper/scieqlint/tree/main/docs"
    )


def test_release_dependency_constraints_are_pinned_and_packaged() -> None:
    constraints = Path(".github/release-constraints.txt").read_text(encoding="utf-8")
    assert {line for line in constraints.splitlines() if line and not line.startswith("#")} == {
        "pip==25.2",
        "build==1.3.0",
        "twine==6.1.0",
        "hatchling==1.27.0",
        "click==8.2.1",
        "pytest==8.4.2",
        "jsonschema==4.25.1",
    }
    assert ".github/release-constraints.txt" in Path("PACK_MANIFEST.md").read_text(encoding="utf-8")


def test_release_workflow_uses_tag_gated_trusted_publishing() -> None:
    workflow = _workflow(Path(".github/workflows/release.yml"))
    assert workflow["concurrency"] == {
        "group": "release-${{ github.ref }}",
        "cancel-in-progress": "true",
    }
    triggers = workflow["on"]
    assert isinstance(triggers, dict)
    assert "workflow_dispatch" in triggers
    push = triggers["push"]
    assert isinstance(push, dict)
    assert push["tags"] == ["v*"]

    build = _workflow_job(workflow, "build")
    _assert_local_release_ref_guard(_step_run(_workflow_step(build, step_id="verify-release-ref")))

    publish = _workflow_job(workflow, "publish")
    assert publish["if"] == "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')"
    assert publish["environment"] == "pypi"
    permissions = publish["permissions"]
    assert isinstance(permissions, dict)
    assert permissions["id-token"] == "write"
    publish_step = _workflow_step(publish, name="Publish to PyPI")
    assert publish_step["uses"] == (
        "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33"
    )
    assert "username" not in publish_step
    assert "password" not in publish_step
    publish_with = publish_step["with"]
    assert isinstance(publish_with, dict)
    assert publish_with == {
        "packages-dir": "dist",
        "verify-metadata": "true",
        "skip-existing": "false",
        "attestations": "true",
        "print-hash": "true",
    }


def test_release_workflow_enforces_version_and_behavioral_evidence() -> None:
    workflow = _workflow(Path(".github/workflows/release.yml"))
    smoke = _workflow_job(workflow, "smoke")
    assert smoke["needs"] == "build"

    version_step = _workflow_step(
        smoke,
        name="Verify source, wheel, source distribution, and stable tag versions",
    )
    version_run = _step_run(version_step)
    assert 'version("scieqlint")' in version_run
    assert "${GITHUB_REF_NAME#v}" in version_run
    assert "sdist_version" in version_run
    assert 'test "$sdist_version" = "$source_version"' in version_run
    assert 'os.environ["SCIEQLINT_RELEASE_SOURCE"]' in version_run
    assert '(source_dir / "pyproject.toml")' in version_run
    assert '(source_dir / "src/scieqlint/__init__.py")' in version_run
    assert '(source_dir / "CITATION.cff")' in version_run
    assert version_run.count("from scieqlint import __version__") == 2
    assert "source __version__ does not match project version" in version_run
    assert "citation version does not match project version" in version_run
    assert "wheel __version__ does not match distribution metadata" in version_run
    assert "sdist __version__ does not match distribution metadata" in version_run
    assert 'Path("pyproject.toml")' not in version_run
    assert (
        r'if [[ "$GITHUB_REF_TYPE" == "tag" && "$GITHUB_REF_NAME" =~ '
        r"^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then"
    ) in version_run
    assert 'if [[ "$GITHUB_REF" == refs/tags/v* ]]' not in version_run

    release_gate = _workflow_step(
        smoke,
        name="Enforce stable-release behavioral evidence",
    )
    assert "if" not in release_gate
    release_gate_run = _step_run(release_gate)
    wheel_dir = "/tmp/scieqlint-release-wheel-smoke"
    sdist_dir = "/tmp/scieqlint-release-sdist-smoke"
    test_targets = (
        "tests/test_accuracy_benchmarks.py",
        "tests/test_generated_formula_quality_golden.py",
        "tests/test_stabilization.py",
    )
    assert _normalized_shell_commands(release_gate_run) == [
        'cd "$SCIEQLINT_RELEASE_SOURCE"',
        (
            f'PIP_CONSTRAINT="$SCIEQLINT_RELEASE_CONSTRAINTS" {wheel_dir}/bin/python '
            f'-m pip install --constraint "$SCIEQLINT_RELEASE_CONSTRAINTS" '
            f'"pytest==8.4.2" "jsonschema==4.25.1"'
        ),
        (
            f"SCIEQLINT_RELEASE_GATE=1 {wheel_dir}/bin/python -m pytest "
            f"-o pythonpath= -q {' '.join(test_targets)}"
        ),
        (
            f'PIP_CONSTRAINT="$SCIEQLINT_RELEASE_CONSTRAINTS" {sdist_dir}/bin/python '
            f'-m pip install --constraint "$SCIEQLINT_RELEASE_CONSTRAINTS" '
            f'"pytest==8.4.2" "jsonschema==4.25.1"'
        ),
        (
            f"SCIEQLINT_RELEASE_GATE=1 {sdist_dir}/bin/python -m pytest "
            f"-o pythonpath= -q {' '.join(test_targets)}"
        ),
    ]


def test_release_workflow_publishes_the_exact_smoke_verified_artifact() -> None:
    workflow = _workflow(Path(".github/workflows/release.yml"))
    build = _workflow_job(workflow, "build")
    smoke = _workflow_job(workflow, "smoke")
    publish = _workflow_job(workflow, "publish")

    build_outputs = build["outputs"]
    assert isinstance(build_outputs, dict)
    build_artifact_id = "${{ steps.release-artifact.outputs.artifact-id }}"
    assert build_outputs["distribution_id"] == build_artifact_id
    assert build_outputs["release_sha"] == "${{ steps.verify-release-ref.outputs.release_sha }}"
    checkout = _workflow_step(
        build,
        uses="actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    )
    checkout_with = checkout["with"]
    assert isinstance(checkout_with, dict)
    assert checkout_with == {
        "fetch-depth": "0",
        "persist-credentials": "false",
    }
    release_ref = _workflow_step(build, step_id="verify-release-ref")
    _assert_local_release_ref_guard(_step_run(release_ref))
    build_guard = _workflow_step(build, name="Verify distribution set")
    _assert_distribution_set_guard(_step_run(build_guard))
    build_run = _step_run(_workflow_step(build, name="Build distribution"))
    assert "PIP_CONSTRAINT" in _workflow_step(build, name="Build distribution")["env"]
    assert '"pip==25.2"' in build_run
    assert '"build==1.3.0"' in build_run
    assert '"twine==6.1.0"' in build_run
    upload = _workflow_step(build, step_id="release-artifact")
    assert upload["uses"] == ("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a")
    assert upload["with"] == {
        "name": "dist",
        "path": "dist/*",
        "if-no-files-found": "error",
        "overwrite": "false",
    }

    assert smoke["needs"] == "build"
    smoke_outputs = smoke["outputs"]
    assert isinstance(smoke_outputs, dict)
    smoke_artifact_id = "${{ needs.build.outputs.distribution_id }}"
    assert smoke_outputs["distribution_id"] == smoke_artifact_id
    assert smoke_outputs["release_sha"] == "${{ needs.build.outputs.release_sha }}"
    smoke_download = _workflow_step(
        smoke,
        uses="actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
    )
    assert smoke_download["with"] == {
        "artifact-ids": smoke_artifact_id,
        "path": "dist",
        "digest-mismatch": "error",
    }
    smoke_steps = smoke["steps"]
    assert isinstance(smoke_steps, list)
    assert not any(
        isinstance(step, dict) and str(step.get("uses", "")).startswith("actions/checkout@")
        for step in smoke_steps
    )
    extraction_run = _step_run(_workflow_step(smoke, name="Extract downloaded source distribution"))
    assert 'find "$GITHUB_WORKSPACE/dist"' in extraction_run
    assert 'tar -xzf "$sdist"' in extraction_run
    assert 'test -f "$source_dir/pyproject.toml"' in extraction_run
    assert 'test -f "$source_dir/tests/test_accuracy_benchmarks.py"' in extraction_run
    assert 'test -f "$source_dir/tests/test_generated_formula_quality_golden.py"' in extraction_run
    assert 'test -f "$source_dir/benchmarks/accuracy/corpus-v1.json"' in extraction_run
    assert 'test -f "$source_dir/.github/release-constraints.txt"' in extraction_run
    assert "SCIEQLINT_RELEASE_SOURCE" in extraction_run
    assert "SCIEQLINT_RELEASE_CONSTRAINTS" in extraction_run
    for step_name, artifact_kind, artifact_glob in (
        ("Clean wheel smoke", "wheel", "*.whl"),
        ("Clean source distribution smoke", "sdist", "*.tar.gz"),
    ):
        commands = _normalized_shell_commands(_step_run(_workflow_step(smoke, name=step_name)))
        artifact_ref = f"${artifact_kind}"
        smoke_dir = f"/tmp/scieqlint-release-{artifact_kind}-smoke"
        assert commands[:7] == [
            (
                f'{artifact_kind}="$(find "$GITHUB_WORKSPACE/dist" -maxdepth 1 '
                f"-type f -name '{artifact_glob}' -print -quit)\""
            ),
            f'test -n "{artifact_ref}"',
            f"python -m venv {smoke_dir}",
            (
                f'PIP_CONSTRAINT="$SCIEQLINT_RELEASE_CONSTRAINTS" '
                f"{smoke_dir}/bin/python -m pip install "
                f'--constraint "$SCIEQLINT_RELEASE_CONSTRAINTS" "{artifact_ref}"'
            ),
            f"{smoke_dir}/bin/python -m pip check",
            f"{smoke_dir}/bin/scieqlint --help",
            f"{smoke_dir}/bin/scieqlint demo",
        ]
        assert f"mechanics preset missing from installed {artifact_kind}" in "\n".join(commands)
    _assert_remote_release_ref_guard(
        _step_run(_workflow_step(smoke, name="Recheck protected main and release tag"))
    )

    assert publish["needs"] == "smoke"
    publish_artifact_id = "${{ needs.smoke.outputs.distribution_id }}"
    publish_download = _workflow_step(
        publish,
        uses="actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
    )
    assert publish_download["with"] == {
        "artifact-ids": publish_artifact_id,
        "path": "dist",
        "digest-mismatch": "error",
    }
    publish_steps = publish["steps"]
    assert isinstance(publish_steps, list)
    assert not any(
        isinstance(step, dict) and str(step.get("uses", "")).startswith("actions/checkout@")
        for step in publish_steps
    )
    assert not any(
        "python -m build" in _step_run(step)
        for step in publish_steps
        if isinstance(step, dict) and "run" in step
    )
    _assert_distribution_set_guard(
        _step_run(_workflow_step(publish, name="Verify final distribution set"))
    )
    _assert_remote_release_ref_guard(
        _step_run(_workflow_step(publish, name="Recheck protected main and release tag"))
    )


def test_release_workflow_rejects_a_missing_protected_main_check() -> None:
    workflow = _parse_workflow(
        """
jobs:
  build:
    steps:
      - id: verify-release-ref
        run: |
          test "$GITHUB_REF_TYPE" = "tag"
          [[ "$GITHUB_REF_NAME" =~ ^v[0-9]+\\.[0-9]+\\.[0-9]+$ ]]
          tag_sha="$(git rev-parse "refs/tags/${GITHUB_REF_NAME}^{commit}")"
          main_sha="$(git rev-parse refs/remotes/origin/main^{commit})"
          test "$tag_sha" = "$RELEASE_SHA"
          printf 'release_sha=%s\\n' "$RELEASE_SHA" >> "$GITHUB_OUTPUT"
"""
    )
    build = _workflow_job(workflow, "build")

    with pytest.raises(AssertionError, match="protected main SHA must be compared"):
        _assert_local_release_ref_guard(
            _step_run(_workflow_step(build, step_id="verify-release-ref"))
        )


def test_release_workflow_rejects_a_tag_recheck_without_expected_sha_match() -> None:
    workflow = _parse_workflow(
        """
jobs:
  smoke:
    steps:
      - name: Recheck protected main and release tag
        run: |
          test "$GITHUB_REF_TYPE" = "tag"
          [[ "$GITHUB_REF_NAME" =~ ^v[0-9]+\\.[0-9]+\\.[0-9]+$ ]]
          test "$EXPECTED_RELEASE_SHA" = "$GITHUB_SHA"
          tag_ref="refs/tags/${GITHUB_REF_NAME}"
          tag_refs="$(git ls-remote --exit-code "$repo_url" "$tag_ref" "${tag_ref}^{}")"
          tag_sha="$(printf '%s\\n' "$tag_refs" | awk -v tag_ref="$tag_ref" 'print $1')"
          main_sha="$(git ls-remote --exit-code "$repo_url" refs/heads/main \
            | awk 'NR == 1 { print $1 }')"
          test "$main_sha" = "$EXPECTED_RELEASE_SHA"
"""
    )
    smoke = _workflow_job(workflow, "smoke")

    with pytest.raises(AssertionError, match="tag SHA must be compared"):
        _assert_remote_release_ref_guard(
            _step_run(_workflow_step(smoke, name="Recheck protected main and release tag"))
        )


def test_release_workflow_rejects_distribution_cardinality_that_allows_extras() -> None:
    workflow = _parse_workflow(
        """
jobs:
  build:
    steps:
      - name: Verify distribution set
        run: |
          shopt -s nullglob
          entries=(dist/* dist/.[!.]* dist/..?*)
          wheels=(dist/*.whl)
          sdists=(dist/*.tar.gz)
          test "${#wheels[@]}" -eq 1
          test "${#sdists[@]}" -eq 1
"""
    )
    build = _workflow_job(workflow, "build")

    with pytest.raises(AssertionError, match="all distribution files must be counted"):
        _assert_distribution_set_guard(
            _step_run(_workflow_step(build, name="Verify distribution set"))
        )


def test_release_workflow_ref_guard_executes_matching_and_rejects_moved_main(
    tmp_path: Path,
) -> None:
    workflow = _workflow(Path(".github/workflows/release.yml"))
    build = _workflow_job(workflow, "build")
    release_run = _step_run(_workflow_step(build, step_id="verify-release-ref"))
    repository = tmp_path / "repo"
    repository.mkdir()

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    git("init", "-q")
    git("checkout", "-q", "-b", "main")
    (repository / "release.txt").write_text("release\n", encoding="utf-8")
    git("add", "release.txt")
    git(
        "-c",
        "commit.gpgSign=false",
        "-c",
        "user.name=Release Test",
        "-c",
        "user.email=release@example.com",
        "commit",
        "-m",
        "release",
        "-q",
    )
    release_sha = git("rev-parse", "HEAD")
    git("-c", "tag.gpgSign=false", "tag", "v1.1.0")
    git("update-ref", "refs/remotes/origin/main", release_sha)

    github_output = tmp_path / "github-output"
    environment = os.environ.copy()
    environment.update(
        {
            "GITHUB_REF_TYPE": "tag",
            "GITHUB_REF_NAME": "v1.1.0",
            "RELEASE_SHA": release_sha,
            "GITHUB_OUTPUT": str(github_output),
        }
    )

    def run_guard() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-euo", "pipefail", "-c", release_run],
            cwd=repository,
            env=environment,
            capture_output=True,
            text=True,
        )

    matching = run_guard()
    assert matching.returncode == 0, matching.stderr
    assert github_output.read_text(encoding="utf-8") == f"release_sha={release_sha}\n"

    (repository / "after-release.txt").write_text("moved\n", encoding="utf-8")
    git("add", "after-release.txt")
    git(
        "-c",
        "commit.gpgSign=false",
        "-c",
        "user.name=Release Test",
        "-c",
        "user.email=release@example.com",
        "commit",
        "-m",
        "move main",
        "-q",
    )
    git("update-ref", "refs/remotes/origin/main", git("rev-parse", "HEAD"))

    moved_main = run_guard()
    assert moved_main.returncode != 0


def test_ci_package_gate_matches_its_documented_artifact_smokes() -> None:
    workflow = _workflow(Path(".github/workflows/ci.yml"))
    package = _workflow_job(workflow, "package")

    build_run = _step_run(_workflow_step(package, name="Build wheel and sdist"))
    source_run = _step_run(_workflow_step(package, name="Test source distribution"))
    smoke_run = _step_run(_workflow_step(package, name="Clean venv smoke test"))
    assert "python -m build" in build_run
    _assert_ci_source_distribution_sequence(source_run)
    assert "/tmp/scieqlint-smoke/bin/python -m pip install dist/*.whl" in smoke_run
    assert "/tmp/scieqlint-smoke/bin/python -m pip install dist/*.tar.gz" not in smoke_run
    assert "/tmp/scieqlint-smoke/bin/scieqlint --help" in smoke_run


def test_ci_package_gate_rejects_checks_before_source_extraction() -> None:
    workflow = _parse_workflow(
        """
jobs:
  package:
    steps:
      - name: Test source distribution
        run: |
          python -m pip install '.[dev]'
          python -m pytest -q
          sdist=\"$(find dist -maxdepth 1 -type f -name '*.tar.gz' -print -quit)\"
          tmpdir=\"$(mktemp -d)\"
          tar -xzf \"$sdist\" -C \"$tmpdir\"
          cd \"$tmpdir\"/scieqlint-*
"""
    )
    package = _workflow_job(workflow, "package")
    source_run = _step_run(_workflow_step(package, name="Test source distribution"))

    with pytest.raises(AssertionError, match="source distribution must be tested"):
        _assert_ci_source_distribution_sequence(source_run)


def test_ci_test_matrix_covers_declared_python_versions() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    workflow = _workflow(Path(".github/workflows/ci.yml"))
    declared_versions = sorted(
        classifier.rsplit(" :: ", 1)[1]
        for classifier in project["classifiers"]
        if classifier.startswith("Programming Language :: Python :: 3.")
    )
    matrix_job = _workflow_job(workflow, "test-matrix")
    strategy = matrix_job["strategy"]
    assert isinstance(strategy, dict)
    matrix = strategy["matrix"]
    assert isinstance(matrix, dict)
    assert declared_versions == ["3.11", "3.12", "3.13"]
    assert matrix["python-version"] == declared_versions
    setup_python = _workflow_step(
        matrix_job,
        uses="actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
    )
    setup_with = setup_python["with"]
    assert isinstance(setup_with, dict)
    assert setup_with["python-version"] == "${{ matrix.python-version }}"
    test_job = _workflow_job(workflow, "test")
    assert test_job["needs"] == ["public-regression-replay", "test-matrix"]
    assert test_job["if"] == "always()"
    pytest_step = _workflow_step(matrix_job, name="Pytest")
    assert pytest_step["if"] == "matrix.python-version != '3.11'"
    coverage_step = _workflow_step(matrix_job, name="Pytest with coverage")
    assert coverage_step["if"] == "matrix.python-version == '3.11'"


def _assert_ci_source_distribution_sequence(source_run: str) -> None:
    lines = source_run.splitlines()

    def line_index(command: str) -> int:
        for index, line in enumerate(lines):
            if line == command:
                return index
        raise AssertionError(f"source distribution must be tested with {command!r}")

    discovery = line_index(
        "sdist=\"$(find dist -maxdepth 1 -type f -name '*.tar.gz' -print -quit)\""
    )
    extraction = line_index('tar -xzf "$sdist" -C "$tmpdir"')
    source_entry = line_index('cd "$tmpdir"/scieqlint-*')
    install = line_index("python -m pip install '.[dev]'")
    tests = line_index("python -m pytest -q")

    assert discovery < extraction < source_entry < install < tests, (
        "source distribution must be tested from extracted source in order"
    )


def _assert_local_release_ref_guard(release_run: str) -> None:
    required = (
        'test "$GITHUB_REF_TYPE" = "tag"',
        '[[ "$GITHUB_REF_NAME" =~ ^v[0-9]+\\.[0-9]+\\.[0-9]+$ ]]',
        'tag_sha="$(git rev-parse "refs/tags/${GITHUB_REF_NAME}^{commit}")"',
        'main_sha="$(git rev-parse refs/remotes/origin/main^{commit})"',
        'test "$tag_sha" = "$RELEASE_SHA"',
        'test "$main_sha" = "$RELEASE_SHA"',
    )
    for fragment in required:
        if fragment not in release_run:
            if fragment == 'test "$main_sha" = "$RELEASE_SHA"':
                raise AssertionError("protected main SHA must be compared with release SHA")
            raise AssertionError(f"release ref guard is missing {fragment!r}")


def _assert_remote_release_ref_guard(release_run: str) -> None:
    required = (
        'test "$GITHUB_REF_TYPE" = "tag"',
        '[[ "$GITHUB_REF_NAME" =~ ^v[0-9]+\\.[0-9]+\\.[0-9]+$ ]]',
        'test "$EXPECTED_RELEASE_SHA" = "$GITHUB_SHA"',
        'tag_ref="refs/tags/${GITHUB_REF_NAME}"',
        "ls-remote --exit-code",
        'tag_sha="$(printf',
        "refs/heads/main",
        'test "$tag_sha" = "$EXPECTED_RELEASE_SHA"',
        'test "$main_sha" = "$EXPECTED_RELEASE_SHA"',
    )
    for fragment in required:
        if fragment not in release_run:
            if fragment == 'test "$tag_sha" = "$EXPECTED_RELEASE_SHA"':
                raise AssertionError("tag SHA must be compared with expected release SHA")
            raise AssertionError(f"remote release ref guard is missing {fragment!r}")


def _assert_distribution_set_guard(distribution_run: str) -> None:
    required = (
        "shopt -s nullglob",
        "entries=(dist/* dist/.[!.]* dist/..?*)",
        "wheels=(dist/*.whl)",
        "sdists=(dist/*.tar.gz)",
        'test "${#entries[@]}" -eq 2',
        'test "${#wheels[@]}" -eq 1',
        'test "${#sdists[@]}" -eq 1',
        'for entry in "${entries[@]}"; do',
        'test -f "$entry"',
    )
    for fragment in required:
        if fragment not in distribution_run:
            if fragment == 'test "${#entries[@]}" -eq 2':
                raise AssertionError("all distribution files must be counted")
            raise AssertionError(f"distribution set guard is missing {fragment!r}")


def _assigned_string(tree: ast.Module, name: str) -> str:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    value = node.value
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        return value.value
    raise AssertionError(f"missing string assignment: {name}")
