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
    gate_line = re.compile(
        rf"^[ \t]*(?:-[ \t]+)?run:[ \t]*[\"']?"
        rf"{re.escape(CI_GATE_COMMAND)}[\"']?[ \t]*(?:#.*)?$"
    )
    status_line = re.compile(r"^[ \t]*(?:-[ \t]+)?(?P<key>[^#\s][^:]*):[ \t]*(?P<value>.*)$")
    mapping_line = re.compile(r"^[ \t]*(?!-[ \t]+)(?P<key>[^#\s][^:]*):[ \t]*(?P<value>.*)$")
    mapping_key = re.compile(r"^[ \t]*(?!-[ \t]+)(?P<key>[^#\s][^:]*):[ \t]*(?:#.*)?$")
    list_item_line = re.compile(r"^[ \t]*-(?:[ \t]+.*)?$")
    block_scalar_header = re.compile(
        r"(?:^|:[ \t]*|-[ \t]+)[|>]"
        r"(?:(?:[1-9][+-]?)|(?:[+-][1-9]?))?[ \t]*$"
    )
    lines = text.splitlines()
    scalar_content_lines: set[int] = set()
    quoted_content_lines: set[int] = set()
    scalar_indent: int | None = None
    quoted_scalar_quote: str | None = None
    for line_index, line in enumerate(lines):
        indent = len(line) - len(line.lstrip())
        if scalar_indent is not None:
            if line.strip() and not line.lstrip().startswith("#") and indent <= scalar_indent:
                scalar_indent = None
            else:
                scalar_content_lines.add(line_index)
                continue
        if quoted_scalar_quote is not None:
            quoted_content_lines.add(line_index)
            quoted_scalar_quote = _yaml_quote_state(line, quoted_scalar_quote)
            continue
        if block_scalar_header.search(_strip_yaml_comment(line).strip()) is not None:
            scalar_indent = indent
            continue
        value = line.lstrip()
        if value.startswith("- "):
            value = value[2:].lstrip()
        colon = value.find(":")
        if colon >= 0:
            value = value[colon + 1 :].lstrip()
        if value.startswith(("'", '"')):
            quoted_scalar_quote = _yaml_quote_state(value)

    # Scalar and quoted continuations are values, never YAML structure.
    ignored_structure_lines = scalar_content_lines | quoted_content_lines
    for index, line in enumerate(lines):
        if index in ignored_structure_lines or gate_line.fullmatch(line) is None:
            continue
        # Derive the containing step and job from their mapping boundaries; YAML
        # nesting is valid with widths other than the repository's usual two spaces.
        gate_indent = len(line) - len(line.lstrip())
        inline_step = line.lstrip().startswith("- ")
        if inline_step:
            step_start = index
        else:
            step_start = -1
            for candidate_index in range(index - 1, -1, -1):
                candidate = lines[candidate_index]
                if candidate_index in ignored_structure_lines:
                    continue
                candidate_indent = len(candidate) - len(candidate.lstrip())
                if candidate_indent < gate_indent and list_item_line.fullmatch(candidate):
                    step_start = candidate_index
                    break
            if step_start < 0:
                continue

        step_indent = len(lines[step_start]) - len(lines[step_start].lstrip())
        steps_start = -1
        steps_indent = -1
        for candidate_index in range(step_start, -1, -1):
            if candidate_index in ignored_structure_lines:
                continue
            candidate_match = mapping_key.fullmatch(lines[candidate_index])
            if candidate_match is None or candidate_match.group("key").strip() != "steps":
                continue
            candidate_indent = len(lines[candidate_index]) - len(lines[candidate_index].lstrip())
            if candidate_indent <= step_indent:
                steps_start = candidate_index
                steps_indent = candidate_indent
                break
        if steps_start < 0:
            continue

        job_start = -1
        job_indent = -1
        for candidate_index in range(steps_start - 1, -1, -1):
            if candidate_index in ignored_structure_lines:
                continue
            candidate_match = mapping_key.fullmatch(lines[candidate_index])
            if candidate_match is None:
                continue
            candidate_indent = len(lines[candidate_index]) - len(lines[candidate_index].lstrip())
            if candidate_indent < steps_indent:
                job_start = candidate_index
                job_indent = candidate_indent
                break
        if job_start < 0:
            continue

        jobs_start = -1
        jobs_indent = -1
        for candidate_index in range(job_start - 1, -1, -1):
            if candidate_index in ignored_structure_lines:
                continue
            candidate_match = mapping_key.fullmatch(lines[candidate_index])
            if candidate_match is None:
                continue
            candidate_indent = len(lines[candidate_index]) - len(lines[candidate_index].lstrip())
            if candidate_indent < job_indent:
                if candidate_match.group("key").strip() == "jobs":
                    jobs_start = candidate_index
                    jobs_indent = candidate_indent
                break
        if jobs_start < 0:
            continue

        for candidate_index in range(jobs_start - 1, -1, -1):
            if candidate_index in ignored_structure_lines:
                continue
            candidate_match = mapping_key.fullmatch(lines[candidate_index])
            if candidate_match is None:
                continue
            candidate_indent = len(lines[candidate_index]) - len(lines[candidate_index].lstrip())
            if candidate_indent < jobs_indent:
                jobs_start = -1
                break
        if jobs_start < 0:
            continue

        direct_step_indent = -1
        for candidate_index in range(steps_start + 1, index + 1):
            if candidate_index in ignored_structure_lines:
                continue
            candidate = lines[candidate_index]
            if not candidate.strip() or candidate.lstrip().startswith("#"):
                continue
            candidate_indent = len(candidate) - len(candidate.lstrip())
            if list_item_line.fullmatch(candidate):
                if candidate_indent >= steps_indent:
                    direct_step_indent = candidate_indent
                break
            break
        if direct_step_indent < 0 or step_indent != direct_step_indent:
            continue

        end = index + 1
        while end < len(lines):
            if end in ignored_structure_lines:
                end += 1
                continue
            candidate = lines[end]
            candidate_indent = len(candidate) - len(candidate.lstrip())
            if candidate_indent == step_indent and list_item_line.fullmatch(candidate):
                break
            end += 1
        step_lines = lines[step_start:end]
        direct_property_indents = {
            len(candidate) - len(candidate.lstrip())
            for candidate_index, candidate in enumerate(step_lines, start=step_start)
            if candidate_index not in ignored_structure_lines
            and len(candidate) - len(candidate.lstrip()) > step_indent
            and mapping_line.fullmatch(candidate)
        }
        direct_property_indent = min(direct_property_indents, default=-1)
        if not inline_step and gate_indent != direct_property_indent:
            continue
        step_property_indents = {step_indent}
        if direct_property_indent >= 0:
            step_property_indents.add(direct_property_indent)
        if not _scope_is_proven_blocking(
            lines=lines,
            ignored_structure_lines=ignored_structure_lines,
            start=step_start,
            end=end,
            property_indents=step_property_indents,
            status_line=status_line,
            reject_needs=False,
        ):
            continue

        job_end = len(lines)
        for candidate_index in range(job_start + 1, len(lines)):
            if candidate_index in ignored_structure_lines:
                continue
            candidate_match = mapping_key.fullmatch(lines[candidate_index])
            if candidate_match is None:
                continue
            candidate_indent = len(lines[candidate_index]) - len(lines[candidate_index].lstrip())
            if candidate_indent == job_indent:
                job_end = candidate_index
                break
        if not _scope_is_proven_blocking(
            lines=lines,
            ignored_structure_lines=ignored_structure_lines,
            start=job_start + 1,
            end=job_end,
            property_indents={steps_indent},
            status_line=status_line,
            reject_needs=True,
        ):
            continue
        return True
    return False


def _scope_is_proven_blocking(
    *,
    lines: list[str],
    ignored_structure_lines: set[int],
    start: int,
    end: int,
    property_indents: set[int],
    status_line: re.Pattern[str],
    reject_needs: bool,
) -> bool:
    seen_status_keys: set[str] = set()
    for index in range(start, end):
        if index in ignored_structure_lines:
            continue
        line = lines[index]
        if len(line) - len(line.lstrip()) not in property_indents:
            continue
        match = status_line.fullmatch(line)
        if match is None:
            continue
        key = match.group("key").strip()
        if len(key) >= 2 and key[0] == key[-1] and key[0] in {"'", '"'}:
            key = key[1:-1].strip()
        key = key.casefold()
        if key in seen_status_keys:
            return False
        if key == "needs" and reject_needs:
            # Reachability through skipped dependencies is not proven here.
            return False
        if key not in {"if", "continue-on-error"}:
            continue
        seen_status_keys.add(key)
        static_bool = _static_workflow_bool(match.group("value"))
        if key == "if" and static_bool is not True:
            return False
        if key == "continue-on-error" and static_bool is not False:
            return False
    return True


def _static_workflow_bool(value: str) -> bool | None:
    value = _strip_yaml_comment(value).strip()
    # Anchors and aliases require YAML resolution; unknown values fail closed.
    if not value or value.startswith(("&", "*")):
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    if value.startswith("${{") and value.endswith("}}"):
        value = value[3:-2].strip()
    normalized = value.casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def _yaml_quote_state(value: str, quote: str | None = None) -> str | None:
    index = 0
    while index < len(value):
        character = value[index]
        if quote is None:
            if character == "#" and (index == 0 or value[index - 1].isspace()):
                break
            if character in {"'", '"'}:
                quote = character
        elif quote == "'" and character == "'":
            if index + 1 < len(value) and value[index + 1] == "'":
                index += 1
            else:
                quote = None
        elif quote == '"':
            if character == "\\":
                index += 1
            elif character == '"':
                quote = None
        index += 1
    return quote


def _strip_yaml_comment(value: str) -> str:
    quote: str | None = None
    index = 0
    while index < len(value):
        character = value[index]
        if quote is None:
            if character in {"'", '"'}:
                quote = character
            elif character == "#" and (index == 0 or value[index - 1].isspace()):
                return value[:index].rstrip()
        elif quote == "'" and character == "'":
            if index + 1 < len(value) and value[index + 1] == "'":
                index += 1
            else:
                quote = None
        elif quote == '"':
            if character == "\\":
                index += 1
            elif character == '"':
                quote = None
        index += 1
    return value.strip()


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
    fenced_code = re.compile(r"(?ms)^(?P<fence>`{3,}|~{3,})[^\n]*\n.*?^(?P=fence)[ \t]*$")
    without_fences = fenced_code.sub(
        lambda match: "\n" * match.group(0).count("\n"),
        text,
    )
    return re.sub(r"`[^`\n]+`", "", without_fences)


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
