"""Deterministic architecture terminology drift scanner."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

COMMAND = "architecture-terminology-drift"
SCHEMA_VERSION = "architecture-terminology-drift/v1"
OWNER = "Architecture conformance tooling"
CI_GATE_COMMAND = "python tools/architecture/terminology_drift.py --format json"
ABSOLUTE_PATH_PLACEHOLDER = "<absolute-path>"
EXIT_STATUS = {
    "0": "pass: inputs are valid, no terminology drift is present, and the release gate is wired",
    "1": "failed: valid inputs contain terminology drift or stale release-gate evidence",
    "2": (
        "invalid-input: a required input is missing, malformed, absolute, or outside the repository"
    ),
}
TERMS = (
    "WorkspaceHost",
    "FrontendHost",
    "MathHost",
    "FactHost",
    "QueryHost",
    "EngineHost",
    "PolicyHost",
    "AnalysisResult",
    "SchemaHost",
    "PackHost",
    "CompatibilityShell",
)
DEFAULT_ARCHITECTURE_DOCS = (
    "docs/architecture.md",
    "docs/architecture/deterministic-snapshot-kernel-adr.md",
    "docs/architecture/module-ownership.md",
)
DEFAULT_MODULE_GRAPH = "pyproject.toml"
DEFAULT_CI_CONFIGS = (".github/workflows/ci.yml",)


@dataclass(frozen=True)
class LoadedInput:
    kind: str
    path: PurePosixPath
    text: str


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    architecture_docs = tuple(args.architecture_doc or DEFAULT_ARCHITECTURE_DOCS)
    module_graph = args.module_graph or DEFAULT_MODULE_GRAPH
    ci_configs = tuple(args.ci_config or DEFAULT_CI_CONFIGS)

    report, exit_code = build_report(root, architecture_docs, module_graph, ci_configs)
    if args.format != "json":
        raise AssertionError("argparse restricts format choices")
    sys.stdout.write(dump_report(report))
    return exit_code


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scan architecture documents, the module graph, and CI configuration for "
            "architecture terminology drift. Exit status: "
            "0 pass; 1 drift or stale gate; 2 missing, malformed, absolute, or escaping input."
        )
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--architecture-doc",
        action="append",
        help="Repo-relative architecture Markdown input. May be repeated.",
    )
    parser.add_argument(
        "--module-graph",
        help="Repo-relative module graph input. Defaults to pyproject.toml.",
    )
    parser.add_argument(
        "--ci-config",
        action="append",
        help="Repo-relative CI configuration input. May be repeated.",
    )
    parser.add_argument(
        "--format",
        default="json",
        choices=("json",),
        help="Machine output format.",
    )
    return parser.parse_args(argv)


def build_report(
    root: Path,
    architecture_docs: tuple[str, ...],
    module_graph: str,
    ci_configs: tuple[str, ...],
) -> tuple[dict[str, Any], int]:
    invalid_inputs: list[dict[str, str]] = []
    loaded: list[LoadedInput] = []
    for kind, values in (
        ("architecture_document", architecture_docs),
        ("module_graph", (module_graph,)),
        ("ci_config", ci_configs),
    ):
        for value in values:
            item = load_input(root, kind, value)
            if isinstance(item, LoadedInput):
                loaded.append(item)
            else:
                invalid_inputs.append(item)

    violations: list[dict[str, Any]] = []
    if invalid_inputs:
        violations.extend(invalid_inputs)
        return base_report(loaded, violations, "invalid-input"), 2

    malformed = validate_loaded_inputs(loaded)
    if malformed:
        violations.extend(malformed)
        return base_report(loaded, violations, "invalid-input"), 2

    violations.extend(scan_drift(loaded))
    violations.extend(scan_release_gate(loaded))
    status = "failed" if violations else "passed"
    exit_code = 1 if violations else 0
    return base_report(loaded, violations, status), exit_code


def load_input(root: Path, kind: str, value: str) -> LoadedInput | dict[str, str]:
    path = Path(value)
    if path.is_absolute():
        return violation(
            "ARCH-TERM-INPUT-ABSOLUTE",
            kind,
            ABSOLUTE_PATH_PLACEHOLDER,
            "absolute input paths are not deterministic",
            "Pass a repository-relative architecture document, module graph, or CI path.",
        )
    normalized = PurePosixPath(path.as_posix())
    if normalized.as_posix() in {"", "."} or ".." in normalized.parts:
        return violation(
            "ARCH-TERM-INPUT-ESCAPE",
            kind,
            normalized.as_posix(),
            "input path is empty or escapes the repository",
            "Pass a stable path inside the repository checkout.",
        )
    full_path = (root / Path(*normalized.parts)).resolve()
    try:
        full_path.relative_to(root)
    except ValueError:
        return violation(
            "ARCH-TERM-INPUT-ESCAPE",
            kind,
            normalized.as_posix(),
            "input path resolves outside the repository",
            "Pass a stable path inside the repository checkout.",
        )
    if not full_path.is_file():
        return violation(
            "ARCH-TERM-INPUT-MISSING",
            kind,
            normalized.as_posix(),
            "required input is missing",
            "Create the required evidence file or pass the correct repo-relative input path.",
        )
    try:
        text = full_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return violation(
            "ARCH-TERM-INPUT-ENCODING",
            kind,
            normalized.as_posix(),
            "required input is not valid UTF-8",
            "Store architecture scanner evidence as UTF-8 text.",
        )
    return LoadedInput(kind=kind, path=normalized, text=text)


def validate_loaded_inputs(loaded: list[LoadedInput]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    by_kind = group_by_kind(loaded)
    if not by_kind.get("architecture_document"):
        violations.append(
            violation(
                "ARCH-TERM-INPUT-MISSING",
                "architecture_document",
                "",
                "no architecture documents were provided",
                "Pass at least one repo-relative architecture Markdown document.",
            )
        )
    for doc in by_kind.get("architecture_document", ()):
        if doc.path.suffix != ".md" or not doc.text.strip().startswith("#"):
            violations.append(
                violation(
                    "ARCH-TERM-INPUT-MALFORMED",
                    doc.kind,
                    doc.path.as_posix(),
                    "architecture document must be Markdown with a heading",
                    "Use checked-in architecture Markdown as scanner input.",
                )
            )

    module_graphs = by_kind.get("module_graph", ())
    if len(module_graphs) != 1:
        violations.append(
            violation(
                "ARCH-TERM-INPUT-MALFORMED",
                "module_graph",
                "",
                "exactly one module graph input is required",
                "Pass pyproject.toml as the module graph evidence input.",
            )
        )
    for module_graph in module_graphs:
        validate_module_graph(module_graph, violations)

    if not by_kind.get("ci_config"):
        violations.append(
            violation(
                "ARCH-TERM-INPUT-MISSING",
                "ci_config",
                "",
                "no CI configuration was provided",
                "Pass the release-gate CI workflow as scanner input.",
            )
        )
    for ci_config in by_kind.get("ci_config", ()):
        if ci_config.path.suffix not in {".yml", ".yaml"}:
            violations.append(
                violation(
                    "ARCH-TERM-INPUT-MALFORMED",
                    ci_config.kind,
                    ci_config.path.as_posix(),
                    "CI configuration must be a YAML workflow file",
                    "Use the checked-in release-gate workflow file.",
                )
            )
    return violations


def validate_module_graph(module_graph: LoadedInput, violations: list[dict[str, Any]]) -> None:
    try:
        parsed = cast(dict[str, object], tomllib.loads(module_graph.text))
    except tomllib.TOMLDecodeError as exc:
        violations.append(
            violation(
                "ARCH-TERM-MODULE-GRAPH-MALFORMED",
                module_graph.kind,
                module_graph.path.as_posix(),
                f"module graph TOML is malformed: {exc}",
                "Fix pyproject.toml so import-linter architecture contracts can be read.",
            )
        )
        return
    tool = parsed.get("tool")
    tool_config = cast(dict[str, object], tool) if isinstance(tool, dict) else {}
    importlinter = tool_config.get("importlinter")
    importlinter_config = (
        cast(dict[str, object], importlinter) if isinstance(importlinter, dict) else {}
    )
    contracts = importlinter_config.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        violations.append(
            violation(
                "ARCH-TERM-MODULE-GRAPH-MISSING",
                module_graph.kind,
                module_graph.path.as_posix(),
                "module graph does not contain import-linter contracts",
                "Keep architecture import-linter contracts in pyproject.toml.",
            )
        )
        return
    for index, contract in enumerate(cast(list[object], contracts)):
        contract_config = cast(dict[str, object], contract) if isinstance(contract, dict) else {}
        if not contract_config or not str(contract_config.get("name", "")).startswith(
            "Owner: architecture boundary map"
        ):
            violations.append(
                violation(
                    "ARCH-TERM-MODULE-GRAPH-MALFORMED",
                    module_graph.kind,
                    module_graph.path.as_posix(),
                    f"import-linter contract {index} is missing the architecture owner prefix",
                    "Name architecture contracts with the durable architecture boundary-map owner.",
                )
            )


def scan_drift(loaded: list[LoadedInput]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for item in loaded:
        if item.kind not in {"architecture_document", "module_graph", "ci_config"}:
            continue
        text = strip_markdown_code(item.text) if item.kind == "architecture_document" else item.text
        for expected in TERMS:
            for observed in drift_spellings(expected):
                pattern = rf"(?<![A-Za-z0-9_]){re.escape(observed)}(?![A-Za-z0-9_])"
                for match in re.finditer(pattern, text):
                    line = text.count("\n", 0, match.start()) + 1
                    violations.append(
                        {
                            "id": "ARCH-TERM-DRIFT",
                            "kind": item.kind,
                            "path": item.path.as_posix(),
                            "line": line,
                            "owner": OWNER,
                            "term": expected,
                            "observed": observed,
                            "message": (
                                f"architecture terminology drift: use {expected}, not {observed}"
                            ),
                            "remediation": (
                                f"Replace {observed} with {expected} in "
                                "architecture-owned evidence."
                            ),
                        }
                    )
    return sorted(violations, key=violation_order)


def scan_release_gate(loaded: list[LoadedInput]) -> list[dict[str, Any]]:
    ci_configs = [item for item in loaded if item.kind == "ci_config"]
    if any(has_blocking_release_gate(item.text) for item in ci_configs):
        return []
    paths = ", ".join(
        item.path.as_posix() for item in sorted(ci_configs, key=lambda item: item.path.as_posix())
    )
    return [
        violation(
            "ARCH-TERM-CI-GATE-MISSING",
            "ci_config",
            paths,
            "release-gate CI does not run the architecture terminology drift scanner",
            f"Add a release-blocking CI step running `{CI_GATE_COMMAND}`.",
        )
    ]


def has_blocking_release_gate(text: str) -> bool:
    # This intentionally proves only canonical gate wiring and direct failure controls.
    # Shell overrides can replace exit propagation, so only the default run shell is
    # evidence; full workflow validity still belongs to GitHub Actions validation.
    lines = text.splitlines()
    ignored: set[int] = set()
    block_indent: int | None = None
    open_quote: str | None = None

    def leading_indent(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    def quote_after_colon(line: str) -> str | None:
        content = line.lstrip(" ")
        if content.startswith("- "):
            content = content[2:].lstrip()
        if content[:1] in {"'", '"'}:
            return None
        colon = content.find(":")
        value = content if colon < 0 else content[colon + 1 :].lstrip()
        if not value or value[0] not in {"'", '"'}:
            return None
        quote = value[0]
        escaped = False
        index = 1
        while index < len(value):
            character = value[index]
            if quote == "'":
                if character == "'":
                    if index + 1 < len(value) and value[index + 1] == "'":
                        index += 2
                        continue
                    return None
            elif character == quote and not escaped:
                return None
            escaped = quote == '"' and character == "\\" and not escaped
            index += 1
        return quote

    def quote_closes(line: str, quote: str) -> bool:
        escaped = False
        index = 0
        while index < len(line):
            character = line[index]
            if quote == "'":
                if character == "'":
                    if index + 1 < len(line) and line[index + 1] == "'":
                        index += 2
                        continue
                    return True
            elif character == quote and not escaped:
                return True
            escaped = quote == '"' and character == "\\" and not escaped
            index += 1
        return False

    for index, line in enumerate(lines):
        if open_quote is not None:
            ignored.add(index)
            if quote_closes(line, open_quote):
                open_quote = None
            continue

        if block_indent is not None:
            if not line.strip():
                ignored.add(index)
                continue
            if leading_indent(line) > block_indent:
                ignored.add(index)
                continue
            block_indent = None

        stripped = line.lstrip(" ")
        if not stripped or stripped.startswith("#") or line.startswith("\t"):
            continue
        if re.search(
            r":[ \t]*[|>](?:[+-]?[0-9]*|[0-9]+[+-]?)[ \t]*(?:#.*)?$",
            stripped,
        ):
            block_indent = leading_indent(line)
        open_quote = quote_after_colon(line)

    def mapping(index: int) -> tuple[int, str, str, bool] | None:
        if index in ignored:
            return None
        line = lines[index]
        if line.startswith("\t"):
            return None
        indent = leading_indent(line)
        content = line[indent:]
        key_indent = indent
        sequence_item = False
        if content.startswith("- "):
            content = content[2:]
            key_indent += 2
            sequence_item = True
        elif content == "-":
            return None
        match = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_-]*):(?:[ \t]+(.*))?",
            content,
        )
        if match is None:
            return None
        return key_indent, match.group(1), match.group(2) or "", sequence_item

    def is_list_item(index: int) -> bool:
        if index in ignored:
            return False
        content = lines[index].lstrip(" ")
        return content == "-" or content.startswith("- ")

    def status_value(value: str) -> bool | None:
        normalized = value.strip()
        if not normalized or normalized[:1] in {"'", '"'}:
            return None
        normalized = re.split(r"[ \t]+#", normalized, maxsplit=1)[0].rstrip()
        lowered = normalized.casefold()
        if lowered in {"true", "false"}:
            return lowered == "true"
        expression_prefix = "$" + "{{"
        if normalized.startswith(expression_prefix) and normalized.endswith("}}"):
            body = normalized[len(expression_prefix) : -2].strip().casefold()
            if body in {"true", "false"}:
                return body == "true"
        return None

    def command_value(value: str) -> str | None:
        normalized = value.strip()
        if normalized[:1] in {"'", '"'}:
            quote = normalized[0]
            closing_quote = normalized.rfind(quote)
            trailing = normalized[closing_quote + 1 :].strip()
            if closing_quote < 1 or (trailing and not trailing.startswith("#")):
                return None
            return normalized[1:closing_quote]
        return re.split(r"[ \t]+#", normalized, maxsplit=1)[0].rstrip()

    def scope_is_blocking(properties: dict[str, list[str]]) -> bool:
        if len(properties.get("if", [])) > 1:
            return False
        if len(properties.get("continue-on-error", [])) > 1:
            return False
        if_value = properties.get("if", [])
        if if_value and status_value(if_value[0]) is not True:
            return False
        continue_value = properties.get("continue-on-error", [])
        return not continue_value or status_value(continue_value[0]) is False

    # Keep the candidate anchored to one root jobs mapping; otherwise a nested or
    # duplicate document can detach the command from the workflow role it proves.
    root_jobs = [
        item
        for index in range(len(lines))
        if (item := mapping(index)) is not None and item[0] == 0 and item[1] == "jobs"
    ]
    has_document_boundary = any(
        index not in ignored
        and re.fullmatch(r"(?:---|\.\.\.)(?:[ \t]*(?:#.*)?)?", lines[index].strip())
        for index in range(len(lines))
    )
    has_workflow_run_defaults = any(
        index not in ignored
        and leading_indent(lines[index]) == 0
        and re.fullmatch(
            r"(?:defaults|'defaults'|\"defaults\")[ \t]*:(?:[ \t]+.*)?",
            lines[index],
        )
        is not None
        for index in range(len(lines))
    )
    if len(root_jobs) != 1 or has_document_boundary or has_workflow_run_defaults:
        return False

    jobs_indent: int | None = None
    job_child_indent: int | None = None
    jobs_closed = False
    job_indent: int | None = None
    job_property_indent: int | None = None
    job_properties: dict[str, list[str]] | None = None
    job_unsupported = False
    gate_steps: list[tuple[dict[str, list[str]], bool, int, int]] = []
    steps_indent: int | None = None
    steps_active = False
    step_child_indent: int | None = None
    step_indent: int | None = None
    step_property_indent: int | None = None
    step_properties: dict[str, list[str]] | None = None
    step_unsupported = False
    step_run_count = 0
    step_gate_count = 0
    job_ids: set[str] = set()
    workflow_unsupported = False
    found_gate = False

    def finish_step() -> None:
        nonlocal step_indent
        nonlocal step_property_indent
        nonlocal step_properties
        nonlocal step_unsupported
        nonlocal step_run_count
        nonlocal step_gate_count
        if step_properties is not None and step_gate_count:
            gate_steps.append(
                (
                    step_properties,
                    step_unsupported,
                    step_run_count,
                    step_gate_count,
                )
            )
        step_indent = None
        step_property_indent = None
        step_properties = None
        step_unsupported = False
        step_run_count = 0
        step_gate_count = 0

    def finish_job() -> bool:
        nonlocal job_indent
        nonlocal job_property_indent
        nonlocal job_properties
        nonlocal job_unsupported
        nonlocal gate_steps
        nonlocal steps_indent
        nonlocal steps_active
        nonlocal step_child_indent
        finish_step()
        accepted = False
        if job_properties is not None and not job_unsupported and scope_is_blocking(job_properties):
            accepted = any(
                run_count == 1
                and gate_count == 1
                and not unsupported
                and scope_is_blocking(properties)
                for properties, unsupported, run_count, gate_count in gate_steps
            )
        job_indent = None
        job_property_indent = None
        job_properties = None
        job_unsupported = False
        gate_steps = []
        steps_indent = None
        steps_active = False
        step_child_indent = None
        return accepted

    def record_step_property(
        item: tuple[int, str, str, bool] | None,
        effective_indent: int,
        content: str,
    ) -> None:
        nonlocal step_property_indent
        nonlocal step_unsupported
        nonlocal step_run_count
        nonlocal step_gate_count
        if step_properties is None:
            return
        if item is None:
            if step_property_indent is None:
                step_property_indent = effective_indent
            normalized_content = content.strip()
            if (
                effective_indent == step_property_indent
                and normalized_content != "-"
                and not normalized_content.startswith("- #")
            ):
                step_unsupported = True
            return
        if step_property_indent is None:
            step_property_indent = item[0]
        if item[0] != step_property_indent:
            return
        key, value = item[1], item[2]
        if key.casefold() in {"run", "if", "continue-on-error", "uses", "shell"} and key not in {
            "run",
            "if",
            "continue-on-error",
            "uses",
            "shell",
        }:
            step_unsupported = True
        if key in step_properties:
            step_unsupported = True
        step_properties.setdefault(key, []).append(value)
        if key in {"uses", "shell"}:
            step_unsupported = True
        if key == "run":
            step_run_count += 1
            if command_value(value) == CI_GATE_COMMAND:
                step_gate_count += 1

    def record_job_property(
        item: tuple[int, str, str, bool] | None,
        effective_indent: int,
        content: str,
    ) -> None:
        nonlocal job_property_indent
        nonlocal job_unsupported
        nonlocal steps_indent
        nonlocal steps_active
        nonlocal step_child_indent
        if job_properties is None:
            return
        if item is None:
            if job_property_indent is None:
                job_property_indent = effective_indent
            if effective_indent == job_property_indent:
                job_unsupported = True
            return
        if job_property_indent is None:
            job_property_indent = item[0]
        if item[0] != job_property_indent:
            return
        key, value = item[1], item[2]
        if key.casefold() in {
            "steps",
            "if",
            "continue-on-error",
            "uses",
            "defaults",
        } and key not in {
            "steps",
            "if",
            "continue-on-error",
            "uses",
            "defaults",
        }:
            job_unsupported = True
        if key in job_properties:
            job_unsupported = True
        job_properties.setdefault(key, []).append(value)
        if key == "steps":
            steps_indent = item[0]
            steps_active = not value.strip() or value.lstrip().startswith("#")
            step_child_indent = None
        else:
            steps_active = False
        if key in {"uses", "defaults"}:
            job_unsupported = True

    for index, line in enumerate(lines):
        if index in ignored:
            continue
        stripped = line.lstrip(" ")
        if not stripped or stripped.startswith("#") or line.startswith("\t"):
            continue
        indent = leading_indent(line)
        item = mapping(index)

        if job_indent is not None and indent <= job_indent:
            found_gate = finish_job() or found_gate
        if step_indent is not None and indent <= step_indent:
            finish_step()

        if job_indent is None:
            if item is not None and item[1] == "jobs":
                if item[0] == 0 and not jobs_closed:
                    jobs_indent = item[0]
                    job_child_indent = None
                continue
            if jobs_indent is not None and item is not None and item[0] == 0:
                jobs_closed = True
                continue
            if jobs_closed:
                continue
            if item is None and job_child_indent is not None and indent == job_child_indent:
                workflow_unsupported = True
                continue
            if item is None or jobs_indent is None or item[0] <= jobs_indent:
                continue
            if job_child_indent is None:
                job_child_indent = item[0]
            if item[0] != job_child_indent:
                continue
            if item[3]:
                workflow_unsupported = True
                continue
            if item[1] in job_ids:
                workflow_unsupported = True
            job_ids.add(item[1])
            job_indent = item[0]
            job_property_indent = None
            job_properties = {}
            job_unsupported = bool(item[2].strip() and not item[2].lstrip().startswith("#"))
            gate_steps = []
            steps_indent = None
            steps_active = False
            step_child_indent = None
            continue

        if (
            steps_active
            and steps_indent is not None
            and is_list_item(index)
            and indent > steps_indent
        ):
            if step_child_indent is None:
                step_child_indent = indent
            if indent == step_child_indent:
                finish_step()
                step_indent = indent
                step_property_indent = None
                step_properties = {}
                step_unsupported = False
                step_run_count = 0
                step_gate_count = 0
                record_step_property(
                    item,
                    item[0] if item is not None else indent + 2,
                    line[indent:] if item is None else line[indent + 2 :],
                )
            continue

        if step_indent is not None:
            record_step_property(item, indent, line[indent:])
            continue

        record_job_property(item, indent, line[indent:])

    if job_indent is not None:
        found_gate = finish_job() or found_gate
    return found_gate and not workflow_unsupported


def drift_spellings(term: str) -> tuple[str, ...]:
    words = re.findall(r"[A-Z][a-z]*|[A-Z]+(?=[A-Z]|$)", term)
    phrase = " ".join(words)
    variants = {
        phrase,
        phrase.lower(),
        "-".join(word.lower() for word in words),
        "_".join(word.lower() for word in words),
    }
    variants.discard(term)
    return tuple(sorted(variants))


def strip_markdown_code(text: str) -> str:
    output: list[str] = []
    pending: list[str] = []
    opener: tuple[str, int] | None = None

    # Preserve the existing fence contract while classifying each input line
    # once. Pending text is emitted unchanged when no closer exists, including
    # a closer longer than the opener, so this performance fix does not absorb
    # issue #251.
    lines = text.split("\n")
    has_final_newline = text.endswith("\n")
    if has_final_newline or not text:
        lines.pop()
    for index, content in enumerate(lines):
        line = content + "\n" if index < len(lines) - 1 or has_final_newline else content
        if opener is None:
            opener = _fence_opener(line)
            if opener is None:
                output.append(line)
                continue
            pending.append(line)
            continue

        pending.append(line)
        if not _is_fence_closer(line, opener):
            continue
        segment = "".join(pending)
        output.append("\n" * segment.count("\n"))
        pending.clear()
        opener = None

    output.extend(pending)
    return re.sub(r"`[^`\n]+`", "", "".join(output))


def _fence_opener(line: str) -> tuple[str, int] | None:
    if not line or line[0] not in {"`", "~"}:
        return None
    marker = line[0]
    length = 1
    while length < len(line) and line[length] == marker:
        length += 1
    return (marker, length) if length >= 3 and line.endswith("\n") else None


def _is_fence_closer(line: str, opener: tuple[str, int]) -> bool:
    marker, length = opener
    candidate = line[:-1] if line.endswith("\n") else line
    run_length = 0
    while run_length < len(candidate) and candidate[run_length] == marker:
        run_length += 1
    return run_length == length and not candidate[run_length:].strip(" \t")


def base_report(
    loaded: list[LoadedInput],
    violations: list[dict[str, Any]],
    status: str,
) -> dict[str, Any]:
    ordered_loaded = sorted(loaded, key=lambda item: (item.kind, item.path.as_posix()))
    ordered_violations = sorted(violations, key=violation_order)
    return {
        "schema_version": SCHEMA_VERSION,
        "command": COMMAND,
        "owner": OWNER,
        "terms": list(TERMS),
        "input_contract": {
            "accepted_kinds": ["architecture_document", "module_graph", "ci_config"],
            "path_policy": "repo-relative UTF-8 text only; absolute and escaping paths are invalid",
            "default_architecture_docs": list(DEFAULT_ARCHITECTURE_DOCS),
            "default_module_graph": DEFAULT_MODULE_GRAPH,
            "default_ci_configs": list(DEFAULT_CI_CONFIGS),
        },
        "output_contract": {
            "format": "json",
            "stable_order": "inputs and violations sort by kind, path, line, id, and term",
            "excluded_fields": ["timestamps", "absolute_host_paths", "environment_specific_values"],
        },
        "exit_status": EXIT_STATUS,
        "inputs": [
            {
                "kind": item.kind,
                "path": item.path.as_posix(),
                "sha256": hashlib.sha256(item.text.encode("utf-8")).hexdigest(),
            }
            for item in ordered_loaded
        ],
        "summary": {
            "status": status,
            "inputs": len(ordered_loaded),
            "violations": len(ordered_violations),
        },
        "violations": ordered_violations,
    }


def dump_report(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def violation(
    code: str,
    kind: str,
    path: str,
    message: str,
    remediation: str,
) -> dict[str, str]:
    return {
        "id": code,
        "kind": kind,
        "path": path,
        "owner": OWNER,
        "message": message,
        "remediation": remediation,
    }


def violation_order(item: dict[str, Any]) -> tuple[str, str, int, str, str]:
    return (
        str(item.get("kind", "")),
        str(item.get("path", "")),
        int(item.get("line", 0)),
        str(item.get("id", "")),
        str(item.get("term", "")),
    )


def group_by_kind(loaded: list[LoadedInput]) -> dict[str, tuple[LoadedInput, ...]]:
    grouped: dict[str, list[LoadedInput]] = {}
    for item in loaded:
        grouped.setdefault(item.kind, []).append(item)
    return {
        kind: tuple(sorted(values, key=lambda item: item.path.as_posix()))
        for kind, values in grouped.items()
    }


if __name__ == "__main__":
    raise SystemExit(main())
