from __future__ import annotations

import re
from pathlib import Path

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

    assert install_step["run"] == "python -m pip install scieqlint==1.1.0"
    assert run_step["run"] == (
        f"set +e; scieqlint check {quote}docs/**/*.md{quote} "
        f"{quote}docs/**/*.ipynb{quote} "
        '--format sarif --output scieqlint.sarif; status=$?; '
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


def test_sarif_upload_example_requires_a_valid_artifact() -> None:
    verify_step = _job_step("scieqlint-sarif", "Verify SARIF output")

    assert verify_step["run"] == (
        "test -s scieqlint.sarif && python -m json.tool scieqlint.sarif >/dev/null"
    )


def test_readme_code_scanning_example_uses_guarded_cli() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    section = readme.split("## Code scanning\n", 1)[1].split("## For contributors\n", 1)[0]

    assert "uses: Kuhai9801/scieqlint@v1.1.0" not in section
    assert (
        'run: set +e; scieqlint check "docs/**/*.md" --format sarif '
        '--output scieqlint.sarif; status=$?; test "$status" -le 1 || exit "$status"'
    ) in section
    assert (
        "run: test -s scieqlint.sarif && python -m json.tool "
        "scieqlint.sarif >/dev/null"
    ) in section


def _top_level_mapping(name: str) -> dict[str, str]:
    section = _section_lines(f"{name}:", indent=0)
    return _parse_mapping(section, indent=2)


def _job_step(job_name: str, step_name: str) -> dict[str, str | dict[str, str]]:
    job_lines = _section_lines(f"  {job_name}:", indent=2)
    step_lines = _section_lines("    steps:", indent=4, source=job_lines)

    current_step: list[str] = []
    for line in step_lines:
        if line.startswith("      - "):
            step = _parse_step(current_step)
            if step.get("name") == step_name:
                return step
            current_step = [line]
        elif current_step:
            current_step.append(line)

    step = _parse_step(current_step)
    if step.get("name") == step_name:
        return step
    raise AssertionError(f"missing workflow step: {step_name}")


def _job_mapping(job_name: str, section_name: str) -> dict[str, str]:
    job_lines = _section_lines(f"  {job_name}:", indent=2)
    section_lines = _section_lines(f"    {section_name}:", indent=4, source=job_lines)
    return _parse_mapping(section_lines, indent=6)


def _section_lines(
    header: str,
    *,
    indent: int,
    source: list[str] | None = None,
) -> list[str]:
    lines = source if source is not None else WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = lines.index(header) + 1
    section: list[str] = []
    for line in lines[start:]:
        if line and not line.startswith(" " * (indent + 1)):
            break
        section.append(line)
    return section


def _parse_step(lines: list[str]) -> dict[str, str | dict[str, str]]:
    step: dict[str, str | dict[str, str]] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("      - "):
            key, value = _split_entry(line.removeprefix("      - "))
            step[key] = value
        elif line.startswith("        with:"):
            step["with"] = _parse_mapping(lines[index + 1 :], indent=10)
        elif line.startswith("        "):
            key, value = _split_entry(line.strip())
            step[key] = value
        index += 1
    return step


def _parse_mapping(lines: list[str], *, indent: int) -> dict[str, str]:
    mapping: dict[str, str] = {}
    prefix = " " * indent
    for line in lines:
        if line.startswith(prefix) and not line.startswith(f"{prefix} "):
            key, value = _split_entry(line.strip())
            mapping[key] = value
    return mapping


def _split_entry(entry: str) -> tuple[str, str]:
    key, value = entry.split(": ", 1)
    return key, value
