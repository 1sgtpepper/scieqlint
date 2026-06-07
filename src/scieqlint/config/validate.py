"""Config validation helpers."""

from __future__ import annotations

from scieqlint.config.model import Config


def validate_config(config: Config) -> tuple[str, ...]:
    """Return validation errors for a loaded config."""
    _ = config
    return ()
