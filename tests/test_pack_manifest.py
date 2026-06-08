from __future__ import annotations

import re
import subprocess
from pathlib import Path


def test_pack_manifest_lists_tracked_files() -> None:
    tracked = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    manifest = Path("PACK_MANIFEST.md").read_text(encoding="utf-8")
    listed = [
        match.group(1)
        for line in manifest.splitlines()
        if (match := re.fullmatch(r"- `(.+)`", line))
    ]

    assert listed == tracked
