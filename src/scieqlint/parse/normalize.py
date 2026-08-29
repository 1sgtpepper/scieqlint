"""Parser-level normalization helpers for the supported v0.1.0 subset."""

from __future__ import annotations


def _splitline_starts(text: str) -> tuple[int, ...]:
    """Index Python split-line boundaries once for repeated local span mapping."""

    starts = [0]
    for line in text.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return tuple(starts)
