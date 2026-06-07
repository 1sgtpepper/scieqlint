#!/usr/bin/env python
"""Smoke-check the scaffold pack."""

from __future__ import annotations

import subprocess
import sys

COMMANDS = [
    [sys.executable, "-m", "compileall", "src"],
    [sys.executable, "-m", "pytest"],
]

for command in COMMANDS:
    print("+", " ".join(command))
    subprocess.run(command, check=True)
