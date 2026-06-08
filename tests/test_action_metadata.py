from __future__ import annotations

from pathlib import Path


def test_action_metadata_is_thin_cli_wrapper() -> None:
    metadata = Path("action.yml").read_text(encoding="utf-8")
    install_command = 'python -m pip install "scieqlint==${{ inputs.package-version }}"'

    assert "using: composite" in metadata
    assert "uses: actions/setup-python@v6" in metadata
    assert install_command in metadata
    assert "run: scieqlint ${{ inputs.args }}" in metadata
    assert 'default: "0.1.5"' in metadata
