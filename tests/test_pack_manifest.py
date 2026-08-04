from __future__ import annotations

import re
import subprocess
from pathlib import Path


def test_pack_manifest_lists_tracked_files() -> None:
    manifest = Path("PACK_MANIFEST.md").read_text(encoding="utf-8")
    listed = [
        match.group(1)
        for line in manifest.splitlines()
        if (match := re.fullmatch(r"- `(.+)`", line))
    ]

    if not Path(".git").exists():
        assert "PACK_MANIFEST.md" in listed
        assert "tests/test_pack_manifest.py" in listed
        return

    tracked = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    assert listed == tracked
