"""Command-line interface for SciEqLint."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

import click

from scieqlint import __version__
from scieqlint.api import check_paths, graph_paths
from scieqlint.config.presets import list_presets, read_preset_text
from scieqlint.diag.catalog import explain_code
from scieqlint.graph.json import render_graph_json
from scieqlint.report.github import GitHubReporter
from scieqlint.report.json import JsonReporter
from scieqlint.report.sarif import SarifReporter
from scieqlint.report.text import TextReporter

DEFAULT_CONFIG = """[project]
root = "."
order = []

[scanner]
markdown = true
inline_math = false
math_fences = true

[parser]
strict_unknowns = false

[checks.algebra]
enabled = true
unknown = "info"
denominator_warnings = true

[checks.references]
enabled = true
missing = "warn"
duplicate_labels = "error"
missing_label_strict = false

[checks.dimension]
mode = "auto"
unknown_variables = "warn"

[checks.symbols]
enabled = false

[baseline]
files = []

[vars]
# m = "M"
# v = "L T^-1"
# theta = "1"

[aliases]
# theta = ["\\theta", "θ"]

[ignore]
files = []

[report]
show_suppressed = false
"""


@click.group(
    name="scieqlint",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, prog_name="scieqlint")
def main() -> None:
    """Deterministic linter for supported scientific-document equations."""


@main.command()
@click.argument("paths", nargs=-1, type=click.Path(path_type=Path))
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "github", "sarif"]),
    default="text",
)
@click.option("--output", "output_path", type=click.Path(path_type=Path), default=None)
@click.option("--no-algebra", is_flag=True, help="Disable algebra checks.")
@click.option("--inline-math", is_flag=True, help="Scan inline math.")
@click.option("--quiet", is_flag=True, help="Suppress empty-success text output.")
@click.option("--strict-unknowns", is_flag=True, help="Report unsupported math as errors.")
@click.option("--absolute-paths", is_flag=True, help="Render absolute diagnostic paths.")
def check(
    paths: tuple[Path, ...],
    config_path: Path | None,
    output_format: str,
    output_path: Path | None,
    no_algebra: bool,
    inline_math: bool,
    quiet: bool,
    strict_unknowns: bool,
    absolute_paths: bool,
) -> None:
    """Check supported files."""
    try:
        result = check_paths(
            paths,
            config_path=config_path,
            no_algebra=no_algebra,
            inline_math=inline_math,
            strict_unknowns=strict_unknowns,
            absolute_paths=absolute_paths,
        )
        if output_format == "json":
            rendered = JsonReporter().render(result)
        elif output_format == "github":
            rendered = GitHubReporter().render(result)
        elif output_format == "sarif":
            rendered = SarifReporter().render(result)
        else:
            rendered = TextReporter(quiet=quiet).render(result)
        _write_output(rendered, output_path, sys.stdout)
        raise SystemExit(result.exit_code())
    except click.ClickException:
        raise
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        raise click.ClickException(str(exc)) from exc


@main.command()
@click.option(
    "--path",
    "config_path",
    type=click.Path(path_type=Path),
    default=Path("scieqlint.toml"),
)
@click.option("--preset", default=None, help="Initialize from a packaged preset.")
def init(config_path: Path, preset: str | None) -> None:
    """Write a default config file."""
    if config_path.exists():
        raise click.ClickException(f"config already exists: {config_path}")
    try:
        content = DEFAULT_CONFIG if preset is None else _preset_text(preset)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    config_path.write_text(content, encoding="utf-8")
    click.echo(f"wrote {config_path}")


@main.group()
def presets() -> None:
    """Inspect packaged config presets."""


@presets.command("list")
def list_preset_names() -> None:
    """List packaged config presets."""
    for name in list_presets():
        click.echo(name)


@presets.command("show")
@click.argument("name")
def show_preset(name: str) -> None:
    """Show a packaged config preset."""
    try:
        click.echo(_preset_text(name), nl=False)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


@main.command()
@click.argument("paths", nargs=-1, type=click.Path(path_type=Path))
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
@click.option("--output", "output_path", type=click.Path(path_type=Path), default=None)
def graph(
    paths: tuple[Path, ...],
    config_path: Path | None,
    output_path: Path | None,
) -> None:
    """Build a graph JSON export."""
    try:
        rendered = render_graph_json(graph_paths(paths, config_path=config_path))
        _write_output(rendered, output_path, sys.stdout)
    except click.ClickException:
        raise
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        raise click.ClickException(str(exc)) from exc


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


def _preset_text(name: str) -> str:
    text = read_preset_text(name)
    return text if text.endswith("\n") else f"{text}\n"


def _write_output(rendered: str, output_path: Path | None, stdout: TextIO) -> None:
    if output_path is None:
        if rendered:
            stdout.write(rendered)
            if not rendered.endswith("\n"):
                stdout.write("\n")
        return
    output_path.write_text(rendered, encoding="utf-8")
