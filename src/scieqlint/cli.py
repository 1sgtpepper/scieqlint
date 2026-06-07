"""Command-line interface for SciEqLint."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

import click

from scieqlint import __version__
from scieqlint.api import check_paths, load_config
from scieqlint.diag.catalog import explain_code
from scieqlint.report.json import JsonReporter
from scieqlint.report.text import TextReporter

DEFAULT_CONFIG = """[project]
root = "."
order = []

[scanner]
markdown = true
inline_math = false
math_fences = true

[checks.algebra]
enabled = true
unknown = "info"
denominator_warnings = true

[checks.references]
enabled = true
missing = "warn"
duplicate_labels = "error"
missing_label_strict = false
"""


@click.group(name="scieqlint", context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="scieqlint")
def main() -> None:
    """Deterministic linter for supported scientific-document equations."""


@main.command()
@click.argument("paths", nargs=-1, type=click.Path(path_type=Path))
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
@click.option("--output", "output_path", type=click.Path(path_type=Path), default=None)
@click.option("--quiet", is_flag=True, help="Suppress empty-success text output.")
def check(
    paths: tuple[Path, ...],
    config_path: Path | None,
    output_format: str,
    output_path: Path | None,
    quiet: bool,
) -> None:
    """Check supported files."""
    try:
        result = check_paths(paths, config_path=config_path)
        if output_format == "json":
            rendered = JsonReporter().render(result)
        else:
            rendered = TextReporter(quiet=quiet).render(result)
        _write_output(rendered, output_path, sys.stdout)
        raise SystemExit(result.exit_code())
    except click.ClickException:
        raise
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        raise click.ClickException(str(exc)) from exc


@main.command()
@click.option("--path", "config_path", type=click.Path(path_type=Path), default=Path("scieqlint.toml"))
def init(config_path: Path) -> None:
    """Write a default config file."""
    if config_path.exists():
        raise click.ClickException(f"config already exists: {config_path}")
    config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    click.echo(f"wrote {config_path}")


@main.command()
def demo() -> None:
    """Show the first public demo examples."""
    click.echo("SciEqLint demo")
    click.echo("")
    click.echo("Wrong scalar equation:")
    click.echo("  (a+b)^2 = a^2 + b^2")
    click.echo("Diagnostic:")
    click.echo("  ALG001 algebraic identity does not hold; left - right = 2*a*b")
    click.echo("")
    click.echo("Broken reference:")
    click.echo("  See {eq}`missing`.")
    click.echo("Diagnostic:")
    click.echo("  REF002 equation reference target not found: missing")


@main.command()
@click.argument("code")
def explain(code: str) -> None:
    """Explain a diagnostic code."""
    explanation = explain_code(code.upper())
    if explanation is None:
        raise click.ClickException(f"unknown diagnostic code: {code}")
    click.echo(explanation)


def _write_output(rendered: str, output_path: Path | None, stdout: TextIO) -> None:
    if output_path is None:
        if rendered:
            stdout.write(rendered)
            if not rendered.endswith("\n"):
                stdout.write("\n")
        return
    output_path.write_text(rendered, encoding="utf-8")
