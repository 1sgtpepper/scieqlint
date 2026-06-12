from __future__ import annotations

from pathlib import Path


def test_action_metadata_is_thin_cli_wrapper() -> None:
    metadata = Path("action.yml").read_text(encoding="utf-8")
    inputs = _input_defaults(metadata)
    steps = _steps(metadata)

    assert "runs:\n  using: composite" in metadata
    assert inputs == {
        "python-version": '"3.11"',
        "package-version": '"1.0.0"',
        "args": '"check ."',
    }
    assert steps == [
        {"name": "Set up Python", "uses": "actions/setup-python@v6"},
        {
            "name": "Install SciEqLint",
            "shell": "bash",
            "env": ["SCIEQLINT_PACKAGE_VERSION: ${{ inputs.package-version }}"],
        },
        {
            "name": "Run SciEqLint",
            "shell": "bash",
            "env": ["SCIEQLINT_ARGS: ${{ inputs.args }}"],
        },
    ]
    assert 'python -m pip install "scieqlint==${{ inputs.package-version }}"' not in metadata
    assert "scieqlint ${{ inputs.args }}" not in metadata
    assert 'subprocess.check_call([sys.executable, "-m", "pip", "install"' in metadata
    assert 'subprocess.check_call(["scieqlint", *args])' in metadata


def _input_defaults(metadata: str) -> dict[str, str]:
    defaults: dict[str, str] = {}
    current_input = ""
    for line in metadata.splitlines():
        if line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":"):
            current_input = line.strip().removesuffix(":")
        elif current_input and line.startswith("    default: "):
            defaults[current_input] = line.removeprefix("    default: ")
    return defaults


def _steps(metadata: str) -> list[dict[str, str | list[str]]]:
    steps: list[dict[str, str | list[str]]] = []
    current: dict[str, str | list[str]] = {}
    in_env = False
    for line in metadata.splitlines():
        stripped = line.strip()
        if stripped.startswith("- name: "):
            if current:
                steps.append(current)
            current = {"name": stripped.removeprefix("- name: ")}
            in_env = False
        elif current and stripped == "env:":
            current["env"] = []
            in_env = True
        elif in_env and current and line.startswith("        ") and ": " in stripped:
            env = current["env"]
            assert isinstance(env, list)
            env.append(stripped)
        elif current and ": " in stripped:
            key, value = stripped.split(": ", 1)
            if key in {"uses", "shell"}:
                current[key] = value
            if key != "env":
                in_env = False
    if current:
        steps.append(current)
    return steps
