from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("path", ("IMPLEMENTATION_STATUS.md", "PACK_MANIFEST.md"))
def test_repository_contract_file_is_shipped(path: str) -> None:
    assert Path(path).is_file()


def test_pack_manifest_matches_repository_inventory() -> None:
    if not Path(".git").exists():
        pytest.skip("repository inventory requires a Git checkout")

    tracked = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    manifest = Path("PACK_MANIFEST.md").read_text(encoding="utf-8")
    listed = [
        match.group(1)
        for line in manifest.splitlines()
        if (match := re.fullmatch(r"- `(.+)`", line))
    ]

    assert listed == tracked
