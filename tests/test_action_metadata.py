from __future__ import annotations

from pathlib import Path


def test_action_metadata_is_thin_cli_wrapper() -> None:
    metadata = Path("action.yml").read_text(encoding="utf-8")
    inputs = _input_defaults(metadata)
    steps = _steps(metadata)

    assert "runs:\n  using: composite" in metadata
    assert inputs == {
        "python-version": '"3.11"',
        "package-version": '"1.1.0"',
        "args": '"check ."',
    }
    assert steps == [
        {"name": "Set up Python", "uses": "actions/setup-python@v6"},
        {
            "name": "Install SciEqLint",
            "shell": "bash",
            "run": 'python -m pip install "scieqlint==${{ inputs.package-version }}"',
        },
        {
            "name": "Run SciEqLint",
            "shell": "bash",
            "run": "scieqlint ${{ inputs.args }}",
        },
    ]


def _input_defaults(metadata: str) -> dict[str, str]:
    defaults: dict[str, str] = {}
    current_input = ""
    for line in metadata.splitlines():
        if line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":"):
            current_input = line.strip().removesuffix(":")
        elif current_input and line.startswith("    default: "):
            defaults[current_input] = line.removeprefix("    default: ")
    return defaults


def _steps(metadata: str) -> list[dict[str, str]]:
    steps: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in metadata.splitlines():
        stripped = line.strip()
        if stripped.startswith("- name: "):
            if current:
                steps.append(current)
            current = {"name": stripped.removeprefix("- name: ")}
        elif current and ": " in stripped:
            key, value = stripped.split(": ", 1)
            if key in {"uses", "shell", "run"}:
                current[key] = value
    if current:
        steps.append(current)
    return steps
