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
FENCE_OPEN_RE = re.compile(r"^[ \t]{0,3}(?P<marker>`{3,}|~{3,})[^\n]*$")
FENCE_CLOSE_RE = re.compile(r"^[ \t]{0,3}(?P<marker>`{3,}|~{3,})[ \t]*$")
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
DISABLED_STEP_RE = re.compile(
    r"^[ \t]*if:[ \t]*(?:\$\{\{[ \t]*)?false(?:[ \t]*\}\})?[ \t]*(?:#.*)?$",
    re.IGNORECASE,
)


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
    nonblocking = re.compile(
        r"^[ \t]*(?:-[ \t]+)?continue-on-error:[ \t]*true[ \t]*(?:#.*)?$",
        re.IGNORECASE,
    )
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if gate_line.fullmatch(line) is None:
            continue
        indent = len(line) - len(line.lstrip())
        step_indent = indent if line.lstrip().startswith("- ") else max(indent - 2, 0)
        start = index
        while start >= 0:
            candidate = lines[start]
            candidate_indent = len(candidate) - len(candidate.lstrip())
            if candidate_indent == step_indent and candidate.lstrip().startswith("- "):
                break
            start -= 1
        end = index + 1
        while end < len(lines):
            candidate = lines[end]
            candidate_indent = len(candidate) - len(candidate.lstrip())
            if candidate_indent == step_indent and candidate.lstrip().startswith("- "):
                break
            end += 1
        step_lines = lines[max(start, 0) : end]
        if not any(
            nonblocking.fullmatch(candidate) or DISABLED_STEP_RE.fullmatch(candidate)
            for candidate in step_lines
        ):
            return True
    return False


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
    masked_lines: list[str] = []
    fenced_lines: list[str] = []
    fence_char: str | None = None
    fence_length = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        if fence_char is None:
            opening = FENCE_OPEN_RE.fullmatch(content)
            if opening is None:
                masked_lines.append(line)
                continue
            marker = opening.group("marker")
            fence_char = marker[0]
            fence_length = len(marker)
            fenced_lines = [line]
            continue

        fenced_lines.append(line)
        closing = FENCE_CLOSE_RE.fullmatch(content)
        if (
            closing is not None
            and closing.group("marker")[0] == fence_char
            and len(closing.group("marker")) >= fence_length
        ):
            masked_lines.extend("\n" * item.count("\n") for item in fenced_lines)
            fenced_lines = []
            fence_char = None
            fence_length = 0

    if fenced_lines:
        masked_lines.extend(fenced_lines)

    without_fences = "".join(masked_lines)
    return INLINE_CODE_RE.sub("", without_fences)


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
