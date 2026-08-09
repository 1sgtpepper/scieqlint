"""Deterministic architecture terminology drift scanner."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from dataclasses import dataclass, field
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
_RELEVANT_GATE_TRIGGERS = frozenset({"push", "pull_request"})
_SUPPORTED_GATE_JOB_KEYS = frozenset(
    {
        "concurrency",
        "container",
        "continue-on-error",
        "defaults",
        "environment",
        "env",
        "if",
        "name",
        "needs",
        "outputs",
        "permissions",
        "runs-on",
        "secrets",
        "services",
        "shell",
        "steps",
        "strategy",
        "timeout-minutes",
        "uses",
        "with",
        "working-directory",
    }
)
_SUPPORTED_GATE_STEP_KEYS = frozenset(
    {
        "continue-on-error",
        "env",
        "id",
        "if",
        "name",
        "run",
        "shell",
        "timeout-minutes",
        "uses",
        "with",
        "working-directory",
    }
)


@dataclass(frozen=True)
class LoadedInput:
    kind: str
    path: PurePosixPath
    text: str


@dataclass
class _GateWorkflow:
    jobs: list[_GateJob]
    relevant_trigger_seen: bool = False
    shell_configured: bool = False
    working_directory: str | None = None
    working_directory_seen: bool = False
    unsupported: bool = False


@dataclass
class _GateJob:
    steps: list[_GateStep]
    runs_on: str | None = None
    runs_on_seen: bool = False
    uses_seen: bool = False
    if_blocking: bool = True
    if_seen: bool = False
    continue_on_error_blocking: bool = True
    continue_on_error_seen: bool = False
    needs_seen: bool = False
    shell_configured: bool = False
    working_directory: str | None = None
    working_directory_seen: bool = False
    unsupported: bool = False


@dataclass
class _GateStep:
    job: _GateJob
    run_count: int = 0
    gate_run_count: int = 0
    uses_seen: bool = False
    if_blocking: bool = True
    if_seen: bool = False
    continue_on_error_blocking: bool = True
    continue_on_error_seen: bool = False
    shell_configured: bool = False
    working_directory: str | None = None
    working_directory_seen: bool = False
    unsupported: bool = False


@dataclass
class _GateFrame:
    indent: int
    kind: str
    job: _GateJob | None = None
    step: _GateStep | None = None
    defaults_owner: str | None = None
    mapping_keys: set[str] = field(default_factory=set)


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


# Keep each candidate's job, step, and defaults path while reading the file once;
# recovering that path with backward and forward scans both loses scope and scales
# quadratically when a workflow contains many gate-looking commands.
def has_blocking_release_gate(text: str) -> bool:
    workflow = _GateWorkflow(jobs=[])
    frames = [_GateFrame(indent=-1, kind="root")]
    block_scalar_indent: int | None = None
    quoted_scalar_quote: str | None = None
    flow_depth = 0

    for line in text.splitlines():
        indent = len(line) - len(line.lstrip())
        leading_whitespace = line[: len(line) - len(line.lstrip(" \t"))]
        if "\t" in leading_whitespace:
            workflow.unsupported = True
            continue

        if block_scalar_indent is not None:
            if line.strip() and not line.lstrip().startswith("#") and indent <= block_scalar_indent:
                block_scalar_indent = None
            else:
                continue

        if quoted_scalar_quote is not None:
            quoted_scalar_quote = _yaml_quote_state(line, quoted_scalar_quote)
            continue

        if flow_depth:
            flow_depth, _ = _yaml_flow_map_transition(line, flow_depth)
            continue

        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.match(r"^(?:---|\.\.\.)(?:\s|$)", line.strip()):
            workflow.unsupported = True
            continue

        while len(frames) > 1 and indent <= frames[-1].indent:
            frames.pop()

        entry = _split_yaml_mapping(line)
        if entry is None:
            workflow.unsupported = True
            continue
        is_list_item, raw_key, value = entry
        entry_indent = indent + 2 if is_list_item else indent
        next_flow_depth, flow_seen = _yaml_flow_map_transition(line, 0)
        if flow_seen and not _yaml_flow_mappings_valid(line):
            workflow.unsupported = True
        parent = frames[-1]

        if parent.kind == "steps" and is_list_item:
            job = parent.job
            if job is None:
                continue
            step = _GateStep(job=job)
            job.steps.append(step)
            frames.append(
                _GateFrame(
                    indent=indent,
                    kind="step",
                    job=job,
                    step=step,
                )
            )
            if raw_key is None:
                step.unsupported = True
            else:
                key = _register_gate_mapping_key(workflow, frames[-1], raw_key)
                if key is None:
                    step.unsupported = True
                else:
                    _record_gate_step_property(step, key, value)
            if flow_seen:
                step.unsupported = True
            flow_depth = next_flow_depth
            if flow_seen:
                continue
            if _is_block_scalar_header(value):
                block_scalar_indent = indent
            elif _yaml_quote_state(value) is not None:
                quoted_scalar_quote = _yaml_quote_state(value)
            elif _is_empty_yaml_mapping_value(value) and key is not None:
                frames.append(
                    _GateFrame(
                        indent=entry_indent,
                        kind="map",
                        job=job,
                        step=step,
                    )
                )
            continue

        if is_list_item:
            if parent.kind == "triggers":
                workflow.unsupported = True
                continue
            list_frame = _GateFrame(
                indent=indent,
                kind="list",
                job=parent.job,
                step=parent.step,
                defaults_owner=parent.defaults_owner,
            )
            frames.append(list_frame)
            if (
                raw_key is not None
                and _register_gate_mapping_key(workflow, list_frame, raw_key) is None
            ):
                workflow.unsupported = True
            flow_depth = next_flow_depth
            continue

        key = _register_gate_mapping_key(workflow, parent, raw_key)
        if key is None:
            workflow.unsupported = True
            continue

        if parent.kind == "root":
            if key == "on":
                relevant_trigger, trigger_value_valid = _trigger_value_result(value)
                workflow.relevant_trigger_seen = relevant_trigger
                if not trigger_value_valid:
                    workflow.unsupported = True
                if flow_seen:
                    flow_depth = next_flow_depth
                elif _is_empty_yaml_mapping_value(value):
                    frames.append(_GateFrame(indent=entry_indent, kind="triggers"))
                elif value.startswith(("&", "*")):
                    workflow.unsupported = True
                else:
                    flow_depth = next_flow_depth
                continue
            if key == "jobs":
                if flow_seen:
                    workflow.unsupported = True
                elif _is_empty_yaml_mapping_value(value):
                    frames.append(_GateFrame(indent=entry_indent, kind="jobs"))
                elif value.startswith(("&", "*")):
                    workflow.unsupported = True
                flow_depth = next_flow_depth
                if not flow_seen and _is_block_scalar_header(value):
                    block_scalar_indent = indent
                continue
            if key == "defaults":
                if flow_seen:
                    workflow.unsupported = True
                elif _is_empty_yaml_mapping_value(value):
                    frames.append(
                        _GateFrame(indent=entry_indent, kind="defaults", defaults_owner="workflow")
                    )
                else:
                    workflow.unsupported = True
                flow_depth = next_flow_depth
                continue
            if flow_seen:
                flow_depth = next_flow_depth
            elif _is_block_scalar_header(value):
                block_scalar_indent = indent
            elif _yaml_quote_state(value) is not None:
                quoted_scalar_quote = _yaml_quote_state(value)
            elif _is_empty_yaml_mapping_value(value) and key is not None:
                frames.append(_GateFrame(indent=entry_indent, kind="map"))
            continue

        if parent.kind == "triggers":
            if key in _RELEVANT_GATE_TRIGGERS:
                workflow.relevant_trigger_seen = True
                if not _is_valid_trigger_event_value(value):
                    workflow.unsupported = True
            if flow_seen:
                flow_depth = next_flow_depth
                continue
            if _is_empty_yaml_mapping_value(value):
                frames.append(_GateFrame(indent=entry_indent, kind="map"))
            continue

        if parent.kind == "jobs":
            if not key:
                workflow.unsupported = True
                continue
            job = _GateJob(steps=[])
            workflow.jobs.append(job)
            if flow_seen:
                job.unsupported = True
            elif _is_empty_yaml_mapping_value(value):
                frames.append(_GateFrame(indent=entry_indent, kind="job", job=job))
            else:
                workflow.unsupported = True
            flow_depth = next_flow_depth
            if not flow_seen and _is_block_scalar_header(value):
                block_scalar_indent = indent
            continue

        if parent.kind == "step":
            step = parent.step
            if step is None:
                continue
            if key is None:
                step.unsupported = True
            else:
                _record_gate_step_property(step, key, value)
                if flow_seen:
                    _mark_gate_flow(workflow, parent, key)
            flow_depth = next_flow_depth
            if flow_seen:
                continue
            if _is_block_scalar_header(value):
                block_scalar_indent = indent
            elif _yaml_quote_state(value) is not None:
                quoted_scalar_quote = _yaml_quote_state(value)
            elif _is_empty_yaml_mapping_value(value):
                frames.append(
                    _GateFrame(
                        indent=entry_indent,
                        kind="map",
                        job=step.job,
                        step=step,
                    )
                )
            continue

        if parent.kind == "job":
            job = parent.job
            if job is None:
                continue
            if key is None:
                job.unsupported = True
            elif key == "steps":
                if flow_seen:
                    _mark_gate_flow(workflow, parent, key)
                elif _is_empty_yaml_mapping_value(value):
                    frames.append(_GateFrame(indent=entry_indent, kind="steps", job=job))
            elif key == "defaults":
                if flow_seen:
                    _mark_gate_flow(workflow, parent, key)
                elif _is_empty_yaml_mapping_value(value):
                    frames.append(
                        _GateFrame(
                            indent=entry_indent,
                            kind="defaults",
                            job=job,
                            defaults_owner="job",
                        )
                    )
                else:
                    job.unsupported = True
            else:
                _record_gate_job_property(job, key, value)
                if flow_seen:
                    _mark_gate_flow(workflow, parent, key)
            flow_depth = next_flow_depth
            if flow_seen:
                continue
            if _is_block_scalar_header(value):
                block_scalar_indent = indent
            elif _yaml_quote_state(value) is not None:
                quoted_scalar_quote = _yaml_quote_state(value)
            elif _is_empty_yaml_mapping_value(value) and key not in {
                "if",
                "continue-on-error",
                "needs",
                "shell",
                "working-directory",
                "<<",
                "steps",
                "defaults",
            }:
                frames.append(
                    _GateFrame(
                        indent=entry_indent,
                        kind="map",
                        job=job,
                    )
                )
            continue

        if parent.kind == "defaults":
            if key == "run":
                if flow_seen:
                    _mark_gate_flow(workflow, parent, key)
                elif _is_empty_yaml_mapping_value(value):
                    frames.append(
                        _GateFrame(
                            indent=entry_indent,
                            kind="defaults_run",
                            job=parent.job,
                            defaults_owner=parent.defaults_owner,
                        )
                    )
                else:
                    _mark_gate_default_unsupported(workflow, parent)
            else:
                _mark_gate_default_unsupported(workflow, parent)
            flow_depth = next_flow_depth
            if flow_seen:
                continue
            if _is_block_scalar_header(value):
                block_scalar_indent = indent
            continue

        if parent.kind == "defaults_run":
            if key is None:
                _mark_gate_default_unsupported(workflow, parent)
            else:
                _record_gate_defaults_run_property(workflow, parent, key, value)
                if flow_seen:
                    _mark_gate_flow(workflow, parent, key)
            flow_depth = next_flow_depth
            if flow_seen:
                continue
            if _is_block_scalar_header(value):
                block_scalar_indent = indent
            continue

        if flow_seen:
            flow_depth = next_flow_depth
        elif _is_block_scalar_header(value):
            block_scalar_indent = indent
        elif _yaml_quote_state(value) is not None:
            quoted_scalar_quote = _yaml_quote_state(value)
        elif _is_empty_yaml_mapping_value(value):
            frames.append(
                _GateFrame(
                    indent=entry_indent,
                    kind="map",
                    job=parent.job,
                    step=parent.step,
                    defaults_owner=parent.defaults_owner,
                )
            )

    if (
        workflow.unsupported
        or workflow.shell_configured
        or not workflow.relevant_trigger_seen
        or flow_depth
        or quoted_scalar_quote is not None
    ):
        return False
    for job in workflow.jobs:
        for step in job.steps:
            if step.run_count != 1 or step.gate_run_count != 1:
                continue
            if not step.if_blocking or not step.continue_on_error_blocking:
                continue
            if step.unsupported or step.shell_configured or step.uses_seen:
                continue
            if (
                job.unsupported
                or job.needs_seen
                or job.shell_configured
                or job.uses_seen
                or not job.runs_on_seen
                or not _is_supported_runs_on(job.runs_on)
            ):
                continue
            if not job.if_blocking or not job.continue_on_error_blocking:
                continue
            working_directory = (
                step.working_directory
                if step.working_directory_seen
                else job.working_directory
                if job.working_directory_seen
                else workflow.working_directory
                if workflow.working_directory_seen
                else None
            )
            if working_directory is not None and not _is_repository_root_directory(
                working_directory
            ):
                continue
            return True
    return False


def _register_gate_mapping_key(
    workflow: _GateWorkflow,
    frame: _GateFrame,
    raw_key: str,
) -> str | None:
    key = _canonical_yaml_key(raw_key)
    if key is None or key in frame.mapping_keys:
        workflow.unsupported = True
        return None
    frame.mapping_keys.add(key)
    return key


def _is_supported_runs_on(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip().casefold()
    if not normalized or normalized in {"null", "~", "true", "false"}:
        return False
    return not normalized.startswith(("[", "{", "&", "*", "!", "${{"))


def _yaml_value_kind(value: str) -> str:
    cleaned = _strip_yaml_comment(value).strip()
    if not cleaned:
        return "empty"
    if cleaned.startswith("{"):
        return (
            "mapping" if cleaned.endswith("}") and _yaml_flow_mappings_valid(cleaned) else "invalid"
        )
    if cleaned.startswith("["):
        return (
            "sequence"
            if cleaned.endswith("]") and _split_yaml_flow_entries(cleaned[1:-1]) is not None
            else "invalid"
        )
    if cleaned.startswith(("&", "*", "!")):
        return "invalid"
    if cleaned[0] in {"'", '"'}:
        return "scalar" if _decode_yaml_scalar(cleaned) is not None else "invalid"
    normalized = cleaned.casefold()
    if normalized in {"null", "~"}:
        return "null"
    if normalized in {"true", "false"}:
        return "boolean"
    if re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", cleaned):
        return "number"
    return "scalar"


def _is_yaml_mapping_or_null(value: str) -> bool:
    return _yaml_value_kind(value) in {"empty", "mapping", "null"}


def _is_yaml_scalar_or_mapping(value: str) -> bool:
    return _yaml_value_kind(value) in {"scalar", "mapping"}


def _is_valid_trigger_event_value(value: str) -> bool:
    return _yaml_value_kind(value) in {"empty", "mapping", "null"}


def _trigger_value_result(value: str) -> tuple[bool, bool]:
    cleaned = _strip_yaml_comment(value).strip()
    if not cleaned:
        return False, True
    if cleaned.startswith("["):
        if not cleaned.endswith("]"):
            return False, False
        entries = _split_yaml_flow_entries(cleaned[1:-1])
        if entries is None:
            return False, False
        return (
            any(_decode_yaml_scalar(item) in _RELEVANT_GATE_TRIGGERS for item in entries),
            True,
        )
    if cleaned.startswith("{"):
        if not cleaned.endswith("}"):
            return False, False
        entries = _split_yaml_flow_entries(cleaned[1:-1])
        if entries is None:
            return False, False
        keys: list[str] = []
        relevant = False
        for item in entries:
            colon = _find_yaml_mapping_colon(item)
            if colon < 0:
                return False, False
            key = _canonical_yaml_key(item[:colon].strip())
            if key is None or key in keys:
                return False, False
            keys.append(key)
            if key in _RELEVANT_GATE_TRIGGERS:
                if not _is_valid_trigger_event_value(item[colon + 1 :]):
                    return False, False
                relevant = True
        return relevant, True
    decoded = _decode_yaml_scalar(cleaned)
    return (decoded in _RELEVANT_GATE_TRIGGERS, decoded is not None)


def _yaml_flow_mapping_keys(value: str) -> list[str] | None:
    keys: list[str] = []
    entries = _split_yaml_flow_entries(value)
    if entries is None:
        return None
    for item in entries:
        colon = _find_yaml_mapping_colon(item)
        if colon < 0:
            return None
        key = _canonical_yaml_key(item[:colon].strip())
        if key is None or key in keys:
            return None
        keys.append(key)
    return keys


def _yaml_flow_mappings_valid(value: str) -> bool:
    quote: str | None = None
    mapping_starts: list[int] = []
    index = 0
    while index < len(value):
        character = value[index]
        if quote is None:
            if value.startswith("${{", index):
                closing = value.find("}}", index + 3)
                if closing < 0:
                    return False
                index = closing + 2
                continue
            if character in {"'", '"'}:
                quote = character
            elif character == "{":
                mapping_starts.append(index)
            elif character == "}":
                if not mapping_starts:
                    return False
                content = value[mapping_starts.pop() + 1 : index]
                if _yaml_flow_mapping_keys(content) is None:
                    return False
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
    return quote is None and not mapping_starts


def _split_yaml_flow_entries(value: str) -> list[str] | None:
    entries: list[str] = []
    start = 0
    quote: str | None = None
    braces = 0
    brackets = 0
    index = 0
    while index < len(value):
        character = value[index]
        if quote is None:
            if character in {"'", '"'}:
                quote = character
            elif character == "{":
                braces += 1
            elif character == "}" and braces:
                braces -= 1
            elif character == "[":
                brackets += 1
            elif character == "]" and brackets:
                brackets -= 1
            elif character == "," and not braces and not brackets:
                entries.append(value[start:index].strip())
                start = index + 1
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
    tail = value[start:].strip()
    if tail or entries:
        entries.append(tail)
    if quote is not None or braces or brackets:
        return None
    return [entry for entry in entries if entry]


def _record_gate_step_property(step: _GateStep, key: str, value: str) -> None:
    if (
        key not in _SUPPORTED_GATE_STEP_KEYS
        or key == "with"
        or (key == "env" and not _is_yaml_mapping_or_null(value))
    ):
        step.unsupported = True
    elif key == "uses":
        step.uses_seen = True
    elif key == "run":
        step.run_count += 1
        if _decode_yaml_scalar(value) == CI_GATE_COMMAND:
            step.gate_run_count += 1
    elif key == "if":
        if step.if_seen:
            step.unsupported = True
        step.if_seen = True
        step.if_blocking = _static_workflow_bool(value) is True
    elif key == "continue-on-error":
        if step.continue_on_error_seen:
            step.unsupported = True
        step.continue_on_error_seen = True
        step.continue_on_error_blocking = _static_workflow_bool(value) is False
    elif key == "shell":
        step.shell_configured = True
    elif key == "working-directory":
        if step.working_directory_seen:
            step.unsupported = True
        step.working_directory_seen = True
        step.working_directory = _decode_yaml_scalar(value)
    elif key in {"needs", "<<"}:
        step.unsupported = True


def _record_gate_job_property(job: _GateJob, key: str, value: str) -> None:
    if (
        key not in _SUPPORTED_GATE_JOB_KEYS
        or key in {"secrets", "with"}
        or (
            key in {"env", "outputs", "permissions", "services", "strategy"}
            and not _is_yaml_mapping_or_null(value)
        )
        or (
            key in {"concurrency", "container", "environment"}
            and not _is_yaml_scalar_or_mapping(value)
        )
    ):
        job.unsupported = True
    elif key == "uses":
        job.uses_seen = True
    elif key == "runs-on":
        if job.runs_on_seen:
            job.unsupported = True
        job.runs_on_seen = True
        job.runs_on = _decode_yaml_scalar(value)
    elif key == "if":
        if job.if_seen:
            job.unsupported = True
        job.if_seen = True
        job.if_blocking = _static_workflow_bool(value) is True
    elif key == "continue-on-error":
        if job.continue_on_error_seen:
            job.unsupported = True
        job.continue_on_error_seen = True
        job.continue_on_error_blocking = _static_workflow_bool(value) is False
    elif key == "needs":
        job.needs_seen = True
    elif key == "shell":
        job.shell_configured = True
    elif key == "working-directory":
        if job.working_directory_seen:
            job.unsupported = True
        job.working_directory_seen = True
        job.working_directory = _decode_yaml_scalar(value)
    elif key == "<<":
        job.unsupported = True


def _record_gate_defaults_run_property(
    workflow: _GateWorkflow,
    frame: _GateFrame,
    key: str,
    value: str,
) -> None:
    if frame.job is None:
        if key == "shell":
            if workflow.shell_configured:
                workflow.unsupported = True
            workflow.shell_configured = True
        elif key == "working-directory":
            if workflow.working_directory_seen:
                workflow.unsupported = True
            workflow.working_directory_seen = True
            workflow.working_directory = _decode_yaml_scalar(value)
        else:
            workflow.unsupported = True
    else:
        job = frame.job
        if key == "shell":
            if job.shell_configured:
                job.unsupported = True
            job.shell_configured = True
        elif key == "working-directory":
            if job.working_directory_seen:
                job.unsupported = True
            job.working_directory_seen = True
            job.working_directory = _decode_yaml_scalar(value)
        else:
            job.unsupported = True


def _mark_gate_default_unsupported(workflow: _GateWorkflow, frame: _GateFrame) -> None:
    if frame.job is None:
        workflow.unsupported = True
    else:
        frame.job.unsupported = True


def _mark_gate_flow(workflow: _GateWorkflow, frame: _GateFrame, key: str) -> None:
    if frame.kind == "step" and key in {
        "run",
        "if",
        "continue-on-error",
        "shell",
        "working-directory",
        "uses",
        "needs",
        "<<",
    }:
        frame.step.unsupported = True
    elif frame.kind == "job" and key in {
        "if",
        "continue-on-error",
        "needs",
        "shell",
        "working-directory",
        "runs-on",
        "uses",
        "steps",
        "defaults",
        "<<",
    }:
        frame.job.unsupported = True
    elif frame.kind in {"defaults", "defaults_run"}:
        _mark_gate_default_unsupported(workflow, frame)


def _split_yaml_mapping(line: str) -> tuple[bool, str | None, str] | None:
    indent = len(line) - len(line.lstrip())
    content = line[indent:]
    is_list_item = content == "-" or content.startswith(("- ", "-\t"))
    if is_list_item:
        content = content[1:].lstrip()
        if not content or content.startswith("#"):
            return True, None, ""
    colon = _find_yaml_mapping_colon(content)
    if colon < 0:
        return (True, None, "") if is_list_item else None
    return is_list_item, content[:colon].strip(), content[colon + 1 :].strip()


def _find_yaml_mapping_colon(value: str) -> int:
    quote: str | None = None
    index = 0
    while index < len(value):
        character = value[index]
        if quote is None:
            if character == "#":
                break
            if character in {"'", '"'}:
                quote = character
            elif character == ":" and (
                index + 1 == len(value) or value[index + 1].isspace() or value[index + 1] in ",[]{}"
            ):
                return index
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
    return -1


def _canonical_yaml_key(raw_key: str) -> str | None:
    return _decode_yaml_scalar(raw_key)


def _decode_yaml_scalar(value: str) -> str | None:
    value = _strip_yaml_comment(value).strip()
    if not value:
        return ""
    if value[0] == "'":
        if len(value) < 2 or value[-1] != "'":
            return None
        return value[1:-1].replace("''", "'")
    if value[0] == '"':
        if len(value) < 2 or value[-1] != '"':
            return None
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, str) else None
    if value.startswith(("&", "*", "!")):
        return None
    return value


def _static_workflow_bool(value: str) -> bool | None:
    value = _strip_yaml_comment(value).strip()
    if not value or value.startswith(("&", "*", "!")):
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return None
    if value.startswith("${{") and value.endswith("}}"):
        value = value[3:-2].strip()
    normalized = value.casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def _is_empty_yaml_mapping_value(value: str) -> bool:
    value = _strip_yaml_comment(value).strip()
    return not value or re.fullmatch(r"&[A-Za-z0-9_-]+", value) is not None


def _is_block_scalar_header(value: str) -> bool:
    value = _strip_yaml_comment(value).strip()
    return re.fullmatch(r"[|>](?:(?:[1-9][+-]?)|(?:[+-][1-9]?))?", value) is not None


def _is_repository_root_directory(value: str | None) -> bool:
    return value in {".", "./"}


def _yaml_flow_map_transition(value: str, depth: int) -> tuple[int, bool]:
    quote: str | None = None
    opened = False
    index = 0
    while index < len(value):
        character = value[index]
        if quote is None:
            if character == "#" and (index == 0 or value[index - 1].isspace()):
                break
            if value.startswith("${{", index):
                closing = value.find("}}", index + 3)
                if closing < 0:
                    break
                index = closing + 2
                continue
            if character in {"'", '"'}:
                quote = character
            elif character == "{":
                depth += 1
                opened = True
            elif character == "}" and depth:
                depth -= 1
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
    return depth, opened


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
