import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import FrozenInstanceError
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from scieqlint.api import check_documents as compatibility_check_documents
from scieqlint.config.model import Config
from scieqlint.diag.ir import DiagnosticIR, RelatedLocation
from scieqlint.diag.model import Diagnostic, Severity, SourceSpan
from scieqlint.engine.base import Engine
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.engine.structure import StructureEngine
from scieqlint.facts.generated import GeneratedProvenanceFact
from scieqlint.facts.math import DisplayMathFact, InlineMathFact, UnknownMathFact
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.facts.project import HiddenExcludedFact, ProjectMemberFact
from scieqlint.facts.reference import (
    EquationLabelFact,
    EquationRefFact,
    GenericRefFact,
    TargetAnchorFact,
)
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.facts.structure import (
    CodeCellFact,
    DirectiveFact,
    FenceFact,
    HeadingFact,
    SectionFact,
    StructureSyntaxIssueFact,
)
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.ir.model import DocumentIR, FrontendResult
from scieqlint.query.host import QueryHost
from scieqlint.schema.result import AnalysisResult
from scieqlint.source.maps import SourceMap

REPO_ROOT = Path(__file__).resolve().parents[1]
IMPORT_BOUNDARY_OWNER = "Owner: architecture boundary map"
ARCHITECTURE_TERM_SCANNER = REPO_ROOT / "tools" / "architecture" / "terminology_drift.py"
DETERMINISTIC_SNAPSHOT_ADR = (
    REPO_ROOT / "docs" / "architecture" / "deterministic-snapshot-kernel-adr.md"
)
ARCHITECTURE_EVIDENCE_REVISION = "e7dbb1f2cdae2485c4027fc8c415da25c0ef9663"


def doc(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def mutate_inline_body(inline: Any) -> None:
    inline.body = "y"


def engine_rule_codes(engine: Engine) -> frozenset[str]:
    return engine.rule_codes


def diagnostic_contract(diagnostic: Diagnostic) -> tuple[object, ...]:
    span = diagnostic.span
    return (
        diagnostic.code,
        diagnostic.severity.value,
        diagnostic.message,
        diagnostic.rule,
        diagnostic.equation,
        diagnostic.detail,
        diagnostic.hint,
        diagnostic.suppressed,
        diagnostic.suppression_reason,
        (
            span.path.as_posix(),
            span.start,
            span.end,
            span.line,
            span.col,
            span.end_line,
            span.end_col,
            span.cell,
            span.cell_line,
        )
        if span is not None
        else None,
    )


def test_pure_core_layers_execute_through_compatibility_shell_and_kernel():
    clean = doc(
        "clean.md",
        "# Clean\n\nSee {ref}`clean-target`.\n\n(clean-target)=\n## Clean Target\n",
    )
    edge = doc(
        "edge.md",
        "# Edge\n\nStandalone code is allowed at the boundary.\n\n```\nraw\n```\n",
    )
    violation = doc(
        "violation.md",
        "#Bad\n\nSee {ref}`missing` and {ref}`target`.\n\n(target)=\n# Duplicate top\n",
    )
    documents = (violation, edge, clean)

    snapshot = MySTFrontend().lower(documents)
    query = QueryHost(snapshot)
    reference_diagnostics = ReferenceEngine().run(query)
    structure_diagnostics = StructureEngine().run(query)
    kernel_diagnostics = tuple(
        diagnostic.to_diagnostic()
        for diagnostic in (*reference_diagnostics, *structure_diagnostics)
    )
    analysis_result = AnalysisResult(
        snapshot=snapshot,
        diagnostics=kernel_diagnostics,
        profiles=("scientific-myst",),
    )
    compatibility_result = compatibility_check_documents(documents, config=Config())

    assert compatibility_result.files_checked == 3
    assert reference_diagnostics
    assert structure_diagnostics
    assert engine_rule_codes(ReferenceEngine()) == frozenset(
        {"REF001", "REF002", "REF004", "REF005", "REF006", "REF007", "REF008"}
    )
    assert "STR005" in engine_rule_codes(StructureEngine())
    assert analysis_result.summary() == {
        "files_checked": 3,
        "facts": len(snapshot.all_facts()),
        "diagnostics": 3,
        "errors": 0,
        "warnings": 2,
        "info": 1,
    }
    assert any(diagnostic.code == "STR003" for diagnostic in kernel_diagnostics)
    engine_codes = engine_rule_codes(ReferenceEngine()) | engine_rule_codes(StructureEngine())
    kernel_output = tuple(map(diagnostic_contract, kernel_diagnostics))
    compatibility_output = tuple(
        diagnostic_contract(diagnostic)
        for diagnostic in compatibility_result.diagnostics
        if diagnostic.code in engine_codes
    )
    assert tuple(sorted(kernel_output, key=repr)) == tuple(sorted(compatibility_output, key=repr))

    shuffled_documents = tuple(reversed(documents))
    shuffled_snapshot = MySTFrontend().lower(shuffled_documents)
    shuffled_query = QueryHost(shuffled_snapshot)
    shuffled_kernel_output = tuple(
        diagnostic_contract(diagnostic.to_diagnostic())
        for diagnostic in (
            *ReferenceEngine().run(shuffled_query),
            *StructureEngine().run(shuffled_query),
        )
    )
    shuffled_compatibility_result = compatibility_check_documents(
        shuffled_documents,
        config=Config(),
    )
    shuffled_compatibility_output = tuple(
        diagnostic_contract(diagnostic)
        for diagnostic in shuffled_compatibility_result.diagnostics
        if diagnostic.code in engine_codes
    )
    assert shuffled_kernel_output == kernel_output
    assert shuffled_compatibility_output == compatibility_output
    assert not any(
        diagnostic.span and diagnostic.span.path.as_posix() == "clean.md"
        for diagnostic in compatibility_result.diagnostics
    )
    assert any(
        diagnostic.span and diagnostic.span.path.as_posix() == "edge.md"
        for diagnostic in compatibility_result.diagnostics
    )
    assert {diagnostic.code for diagnostic in compatibility_result.diagnostics} == {
        "REF004",
        "STR001",
        "STR003",
    }


def import_linter_contracts() -> dict[str, dict[str, Any]]:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    contracts = project["tool"]["importlinter"]["contracts"]
    return {contract["name"]: contract for contract in contracts}


def contract_by_suffix(suffix: str) -> dict[str, Any]:
    matches = [
        contract for name, contract in import_linter_contracts().items() if name.endswith(suffix)
    ]
    assert len(matches) == 1
    return matches[0]


def test_import_linter_contracts_encode_release_boundary_map():
    contracts = import_linter_contracts()

    assert all(name.startswith(IMPORT_BOUNDARY_OWNER) for name in contracts)
    assert all("ignored_imports" not in contract for contract in contracts.values())

    engine_contract = contract_by_suffix("Engines consume query facts only")
    assert engine_contract["type"] == "forbidden"
    assert engine_contract["source_modules"] == ["scieqlint.engine"]
    assert set(engine_contract["forbidden_modules"]) >= {
        "scieqlint.scan",
        "scieqlint.parse",
        "scieqlint.compat",
        "scieqlint.frontend",
        "scieqlint.io",
        "scieqlint.source",
        "scieqlint.report",
        "scieqlint.cli",
        "scieqlint.app",
        "scieqlint.api",
    }
    assert engine_contract["allow_indirect_imports"] is True

    reporter_contract = contract_by_suffix("Reporters render only diagnostics")
    assert reporter_contract["type"] == "forbidden"
    assert reporter_contract["source_modules"] == ["scieqlint.report"]
    assert set(reporter_contract["forbidden_modules"]) >= {
        "scieqlint.io",
        "scieqlint.source",
        "scieqlint.scan",
        "scieqlint.parse",
        "scieqlint.check",
        "scieqlint.frontend",
        "scieqlint.engine",
    }


def test_import_linter_ci_gate_is_release_blocking():
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "Import boundaries (release blocking)" in workflow
    assert "run: lint-imports --config pyproject.toml" in workflow
    assert "lint-imports ||" not in workflow
    assert "continue-on-error" not in workflow


def test_import_linter_failure_names_owner_contract_and_modules(tmp_path: Path):
    package = tmp_path / "samplepkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "engine.py").write_text("from samplepkg import scan\n", encoding="utf-8")
    (package / "scan.py").write_text("", encoding="utf-8")
    config = tmp_path / "importlinter.toml"
    contract_name = "Owner: architecture boundary map - sample engine boundary violation"
    config.write_text(
        f"""
[tool.importlinter]
root_package = "samplepkg"

[[tool.importlinter.contracts]]
name = "{contract_name}"
type = "forbidden"
source_modules = ["samplepkg.engine"]
forbidden_modules = ["samplepkg.scan"]
""".lstrip(),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        path for path in (str(tmp_path), env.get("PYTHONPATH", "")) if path
    )
    lint_imports = Path(sys.executable).with_name("lint-imports")
    assert lint_imports.is_file()
    result = subprocess.run(
        [str(lint_imports), "--config", str(config), "--no-cache"],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert contract_name in output
    assert "samplepkg.engine" in output
    assert "samplepkg.scan" in output


def run_architecture_term_scanner(
    *args: str,
    cwd: Path = REPO_ROOT,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ARCHITECTURE_TERM_SCANNER), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def test_architecture_terminology_scanner_emits_stable_machine_report():
    first = run_architecture_term_scanner("--format", "json")
    second = run_architecture_term_scanner("--format", "json")

    assert first.returncode == 0
    assert second.returncode == 0
    assert first.stdout == second.stdout

    report = json.loads(first.stdout)
    assert report["schema_version"] == "architecture-terminology-drift/v1"
    assert report["command"] == "architecture-terminology-drift"
    assert report["owner"] == "Architecture conformance tooling"
    assert report["terms"] == [
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
    ]
    assert report["summary"] == {"status": "passed", "inputs": 5, "violations": 0}
    assert report["exit_status"] == {
        "0": (
            "pass: inputs are valid, no terminology drift is present, and the release gate is wired"
        ),
        "1": "failed: valid inputs contain terminology drift or stale release-gate evidence",
        "2": (
            "invalid-input: a required input is missing, malformed, absolute, "
            "or outside the repository"
        ),
    }
    assert all(Path(item["path"]).is_absolute() is False for item in report["inputs"])
    assert '"timestamp":' not in first.stdout.lower()
    assert str(REPO_ROOT) not in first.stdout


def test_deterministic_snapshot_adr_pins_links_and_separates_evidence_from_plans():
    adr = DETERMINISTIC_SNAPSHOT_ADR.read_text(encoding="utf-8")

    assert "Traceability issue: [GitHub #133]" in adr
    assert "R1-001 / GitHub #133" not in adr
    file_links = re.findall(
        r"https://github\.com/1sgtpepper/scieqlint/(?:blob|tree)/[^)]+",
        adr,
    )
    assert file_links
    assert all(f"/{ARCHITECTURE_EVIDENCE_REVISION}/" in link for link in file_links)
    all_links = re.findall(r"\[[^]]+\]\(([^)]+)\)", adr)
    assert not [
        link for link in all_links if not link.startswith(("http://", "https://", "#", "mailto:"))
    ]

    assert "The current R1 governance evidence is recorded by the merged" in adr
    for pull_request in (216, 217, 218, 219, 220, 289):
        assert f"PR #{pull_request}" in adr
    assert "These links identify completed evidence" in adr
    assert "remaining WorkspaceHost gates: [R1-005B #139]" in adr
    assert "remaining FrontendHost gates: [R1-025 #162]" in adr

    stale_architecture_reservations = (
        "R1-002A #134",
        "R1-002B #135",
        "R2-094C #258",
        "R2-117A #294",
        "R2-118A #296",
        "R2-120 #299",
        "R2-121A #300",
        "R2-125A #305",
        "R2-126A #307",
        "R2-127A #309",
        "R2-128A #311",
        "R2-130 #315",
        "R2-132 #317",
        "R2-133A #318",
        "R2-133B #319",
        "R3-193 #391",
        "R3-196 #395",
    )
    assert all(reservation not in adr for reservation in stale_architecture_reservations)


def test_architecture_terminology_scanner_rejects_missing_input():
    result = run_architecture_term_scanner(
        "--architecture-doc",
        "docs/architecture.md",
        "--module-graph",
        "missing-pyproject.toml",
        "--ci-config",
        ".github/workflows/ci.yml",
        "--format",
        "json",
    )

    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["summary"]["status"] == "invalid-input"
    assert report["violations"] == [
        {
            "id": "ARCH-TERM-INPUT-MISSING",
            "kind": "module_graph",
            "message": "required input is missing",
            "owner": "Architecture conformance tooling",
            "path": "missing-pyproject.toml",
            "remediation": (
                "Create the required evidence file or pass the correct repo-relative input path."
            ),
        }
    ]


def test_architecture_terminology_scanner_rejects_absolute_input_without_host_path():
    result = run_architecture_term_scanner(
        "--architecture-doc",
        str(REPO_ROOT / "docs" / "architecture.md"),
        "--module-graph",
        "pyproject.toml",
        "--ci-config",
        ".github/workflows/ci.yml",
        "--format",
        "json",
    )

    assert result.returncode == 2
    assert str(REPO_ROOT) not in result.stdout
    report = json.loads(result.stdout)
    assert report["summary"]["status"] == "invalid-input"
    assert report["violations"] == [
        {
            "id": "ARCH-TERM-INPUT-ABSOLUTE",
            "kind": "architecture_document",
            "message": "absolute input paths are not deterministic",
            "owner": "Architecture conformance tooling",
            "path": "<absolute-path>",
            "remediation": (
                "Pass a repository-relative architecture document, module graph, or CI path."
            ),
        }
    ]


def test_architecture_terminology_scanner_rejects_malformed_module_graph(tmp_path: Path):
    fixture = write_architecture_term_fixture(tmp_path, ci_gate=True)
    (fixture / "pyproject.toml").write_text("[tool.importlinter\n", encoding="utf-8")

    result = run_architecture_term_scanner("--root", str(fixture), "--format", "json")

    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["summary"]["status"] == "invalid-input"
    assert report["violations"][0]["id"] == "ARCH-TERM-MODULE-GRAPH-MALFORMED"
    assert report["violations"][0]["kind"] == "module_graph"
    assert report["violations"][0]["path"] == "pyproject.toml"
    assert report["violations"][0]["owner"] == "Architecture conformance tooling"
    assert "module graph TOML is malformed" in report["violations"][0]["message"]
    assert report["violations"][0]["remediation"] == (
        "Fix pyproject.toml so import-linter architecture contracts can be read."
    )


def test_architecture_terminology_scanner_reports_drift_and_owner(tmp_path: Path):
    fixture = write_architecture_term_fixture(tmp_path, ci_gate=True)
    (fixture / "docs" / "architecture.md").write_text(
        "# Architecture\n\nThe workspace host owns path policy.\n",
        encoding="utf-8",
    )

    result = run_architecture_term_scanner("--root", str(fixture), "--format", "json")

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["summary"]["status"] == "failed"
    assert report["violations"] == [
        {
            "id": "ARCH-TERM-DRIFT",
            "kind": "architecture_document",
            "line": 3,
            "message": "architecture terminology drift: use WorkspaceHost, not workspace host",
            "observed": "workspace host",
            "owner": "Architecture conformance tooling",
            "path": "docs/architecture.md",
            "remediation": (
                "Replace workspace host with WorkspaceHost in architecture-owned evidence."
            ),
            "term": "WorkspaceHost",
        }
    ]


def test_architecture_terminology_scanner_preserves_lines_while_ignoring_code(
    tmp_path: Path,
):
    fixture = write_architecture_term_fixture(tmp_path, ci_gate=True)
    (fixture / "docs" / "architecture.md").write_text(
        "# Architecture\n\n```text\nworkspace host\n```\n\nThe query host owns views.\n",
        encoding="utf-8",
    )

    result = run_architecture_term_scanner("--root", str(fixture), "--format", "json")

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert [(item["term"], item["line"]) for item in report["violations"]] == [("QueryHost", 7)]


@pytest.mark.parametrize(
    ("case_name", "ci_text", "expected_gate_violation"),
    [
        (
            "comment is not a gate",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      # run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "step continue-on-error",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - continue-on-error: true
        run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "step literal false condition",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - if: false
        run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "step false expression",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - if: ${{ false }}
        run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "case-mismatched step if is not a gate",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - IF: false
        run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "case-mismatched step continue-on-error is not a gate",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - CONTINUE-ON-ERROR: true
        run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "parent job literal false condition",
            """name: CI
on: [push]

jobs:
  quality:
    if: false
    runs-on: ubuntu-latest
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "case-mismatched parent job if is not a gate",
            """name: CI
on: [push]

jobs:
  quality:
    IF: false
    runs-on: ubuntu-latest
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "case-mismatched parent continue-on-error is not a gate",
            """name: CI
on: [push]

jobs:
  quality:
    CONTINUE-ON-ERROR: true
    runs-on: ubuntu-latest
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "parent job continue-on-error",
            """name: CI
on: [push]

jobs:
  quality:
    continue-on-error: true
    runs-on: ubuntu-latest
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "step false continue-on-error is blocking",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - continue-on-error: false
        run: python tools/architecture/terminology_drift.py --format json
""",
            False,
        ),
        (
            "step true condition is blocking",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - if: true
        run: python tools/architecture/terminology_drift.py --format json
""",
            False,
        ),
        (
            "step true condition expression is blocking",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - if: ${{ true }}
        run: python tools/architecture/terminology_drift.py --format json
""",
            False,
        ),
        (
            "parent job false continue-on-error is blocking",
            """name: CI
on: [push]

jobs:
  quality:
    continue-on-error: false
    runs-on: ubuntu-latest
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
""",
            False,
        ),
        (
            "parent job true condition is blocking",
            """name: CI
on: [push]

jobs:
  quality:
    if: true
    runs-on: ubuntu-latest
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
""",
            False,
        ),
        (
            "parent job false continue-on-error expression is blocking",
            """name: CI
on: [push]

jobs:
  quality:
    continue-on-error: ${{ false }}
    runs-on: ubuntu-latest
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
""",
            False,
        ),
        (
            "parent false condition after steps is nonblocking",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
    if: false
""",
            True,
        ),
        (
            "four-space parent job false condition",
            """name: CI
on: [push]

jobs:
    quality:
        if: false
        runs-on: ubuntu-latest
        steps:
            - run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "four-space parent job continue-on-error",
            """name: CI
on: [push]

jobs:
    quality:
        continue-on-error: true
        runs-on: ubuntu-latest
        steps:
            - run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "four-space enabled parent job",
            """name: CI
on: [push]

jobs:
    quality:
        runs-on: ubuntu-latest
        steps:
            - run: python tools/architecture/terminology_drift.py --format json
""",
            False,
        ),
        (
            "unknown step condition is not proof",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - if: ${{ github.ref == 'refs/heads/main' }}
        run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "unknown parent job condition is not proof",
            """name: CI
on: [push]

jobs:
  quality:
    if: ${{ github.ref == 'refs/heads/main' }}
    runs-on: ubuntu-latest
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "unknown continue-on-error is not proof",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - continue-on-error: ${{ matrix.allow_failure }}
        run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "quoted direct status key is not proof",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - "if": false
        run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "aliased continue-on-error is not proof",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - run: optional-check
        continue-on-error: &optional true
      - run: python tools/architecture/terminology_drift.py --format json
        continue-on-error: *optional
""",
            True,
        ),
        (
            "nested status properties are unrelated",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          if: false
          continue-on-error: true
      - run: python tools/architecture/terminology_drift.py --format json
""",
            False,
        ),
        (
            "named direct run step is canonical",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - name: architecture gate
        run: python tools/architecture/terminology_drift.py --format json
""",
            False,
        ),
        (
            "step shell override is not blocking evidence",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - shell: bash -c 'source "$1" || true' -- {0}
        run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "job run defaults are not blocking evidence",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    defaults:
      run:
        shell: bash -c 'source "$1" || true' -- {0}
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "workflow run defaults are not blocking evidence",
            """name: CI
on: [push]
defaults:
  run:
    shell: bash -c 'source "$1" || true' -- {0}

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "quoted job boundary stays in the disabled job",
            """name: CI
on: [push]

jobs:
  quality:
    if: false
    runs-on: ubuntu-latest
    name: "x
  fake:
    y"
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "quoted step boundary stays in the disabled step",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - if: false
        name: "x
      - fake:
        y"
        run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "block scalar command is not a gate",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - name: documentation
        run: |
          run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "explicitly indented block scalar command is not a gate",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - run: |2-
        run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "escaped quote does not end quoted job content",
            r"""name: CI
on: [push]

jobs:
  quality:
    if: false
    runs-on: ubuntu-latest
    name: "x
  fake:
    y \"
  decoy:
    z"
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "escaped quote does not end quoted step content",
            r"""name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - if: false
        name: "x
      - fake:
        y \"
      - decoy:
        z"
        run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "nested with run is not a gate",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - name: decoy
        with:
          run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "nested list run is not a gate",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - name: decoy
        with:
          options:
            - run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "missing mapping separation is not a gate",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - run:python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "case-mismatched run key is not a gate",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - RUN: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "quoted command value is canonical",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - run: "python tools/architecture/terminology_drift.py --format json" # exact command
""",
            False,
        ),
        (
            "unrelated optional step does not change the gate",
            """name: CI
on: [push]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - run: optional-check
        continue-on-error: true
      - run: python tools/architecture/terminology_drift.py --format json
""",
            False,
        ),
        (
            "nested jobs mapping is not a workflow gate",
            """name: CI
config:
  jobs:
    quality:
      steps:
        - run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "duplicate steps mapping is not a gate",
            """name: CI
jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
    steps:
      - run: echo decoy
""",
            True,
        ),
        (
            "plain scalar continuation is not a gate",
            """name: CI
jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
        continuation
""",
            True,
        ),
        (
            "list-shaped jobs mapping is not a gate",
            """name: CI
jobs:
  - quality:
      runs-on: ubuntu-latest
      steps:
        - run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "duplicate root jobs mapping is not a gate",
            """name: CI
jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
jobs:
  decoy:
    steps:
      - run: echo decoy
""",
            True,
        ),
        (
            "duplicate job id is not a gate",
            """name: CI
jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
  quality:
    steps:
      - run: echo decoy
""",
            True,
        ),
        (
            "stray job entry is not a gate",
            """name: CI
jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
  stray
""",
            True,
        ),
        (
            "nested mapping after jobs is not a gate",
            """name: CI
jobs:
  quality:
    if: false
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
config:
  fake:
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
        (
            "multiple YAML documents are not a gate",
            """name: CI
jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
---
name: decoy
""",
            True,
        ),
        (
            "reusable job with local steps is not a gate",
            """name: CI
jobs:
  quality:
    uses: org/repo/.github/workflows/reusable.yml@main
    steps:
      - run: python tools/architecture/terminology_drift.py --format json
""",
            True,
        ),
    ],
)
def test_architecture_terminology_scanner_requires_direct_blocking_gate(
    tmp_path: Path,
    case_name: str,
    ci_text: str,
    expected_gate_violation: bool,
):
    fixture = write_architecture_term_fixture(tmp_path, ci_gate=True)
    (fixture / ".github" / "workflows" / "ci.yml").write_text(
        ci_text,
        encoding="utf-8",
    )

    result = run_architecture_term_scanner("--root", str(fixture), "--format", "json")

    assert result.returncode == int(expected_gate_violation), case_name
    report = json.loads(result.stdout)
    assert [item["id"] for item in report["violations"]] == (
        ["ARCH-TERM-CI-GATE-MISSING"] if expected_gate_violation else []
    ), case_name


def test_architecture_terminology_scanner_fails_when_release_gate_is_missing(
    tmp_path: Path,
):
    fixture = write_architecture_term_fixture(tmp_path, ci_gate=False)

    result = run_architecture_term_scanner("--root", str(fixture), "--format", "json")

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["violations"] == [
        {
            "id": "ARCH-TERM-CI-GATE-MISSING",
            "kind": "ci_config",
            "message": ("release-gate CI does not run the architecture terminology drift scanner"),
            "owner": "Architecture conformance tooling",
            "path": ".github/workflows/ci.yml",
            "remediation": (
                "Add a release-blocking CI step running "
                "`python tools/architecture/terminology_drift.py --format json`."
            ),
        }
    ]


def write_architecture_term_fixture(root: Path, *, ci_gate: bool) -> Path:
    docs = root / "docs" / "architecture"
    docs.mkdir(parents=True)
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (root / "docs" / "architecture.md").write_text(
        "# Architecture\n\nWorkspaceHost\n",
        encoding="utf-8",
    )
    (docs / "deterministic-snapshot-kernel-adr.md").write_text(
        "# ADR\n\nFrontendHost MathHost FactHost QueryHost EngineHost PolicyHost AnalysisResult\n",
        encoding="utf-8",
    )
    (docs / "module-ownership.md").write_text(
        "# Module Ownership\n\nSchemaHost PackHost CompatibilityShell\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        """
[tool.importlinter]
root_package = "scieqlint"

[[tool.importlinter.contracts]]
name = "Owner: architecture boundary map - fixture"
type = "forbidden"
source_modules = ["scieqlint.engine"]
forbidden_modules = ["scieqlint.scan"]
""".lstrip(),
        encoding="utf-8",
    )
    gate = "python tools/architecture/terminology_drift.py --format json" if ci_gate else "pytest"
    (workflows / "ci.yml").write_text(
        (
            "name: CI\n"
            "on: [push]\n"
            "\n"
            "jobs:\n"
            "  quality:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            f"      - run: {gate}\n"
        ),
        encoding="utf-8",
    )
    return root


def span(path: str = "a.md", *, start: int = 0, end: int = 1) -> SourceSpan:
    return SourceSpan(
        path=PurePosixPath(path),
        start=start,
        end=end,
        line=1,
        col=start + 1,
        end_line=1,
        end_col=end,
    )


def test_fact_snapshot_is_deterministic_and_immutable():
    document = doc("a.md", "# Title\n\nText $x$.\n")
    inline = InlineMathFact(
        fact_id="a.md::inline-math::16",
        document_id="a.md",
        span=None,
        raw="$x$",
        body="x",
        delimiter_kind="dollar",
        context="paragraph",
    )

    snapshot = FactSnapshot(documents=(document,), inline_math=(inline,))

    assert snapshot == FactSnapshot(documents=(document,), inline_math=(inline,))
    assert snapshot.documents[0].path.as_posix() == "a.md"
    assert snapshot.all_facts() == (inline,)
    with pytest.raises(FrozenInstanceError):
        mutate_inline_body(inline)


def test_source_map_spans_use_document_offsets():
    document = doc("chapter.md", "alpha\nbeta\n")
    source_map = SourceMap.for_document(document)

    span = source_map.span(6, 10)

    assert source_map.identity.document_id == "chapter.md"
    assert source_map.identity.kind == DocumentKind.MARKDOWN.value
    assert span.path.as_posix() == "chapter.md"
    assert (span.start, span.end) == (6, 10)
    assert (span.line, span.col, span.end_line, span.end_col) == (2, 1, 2, 4)
    with pytest.raises(ValueError, match="invalid span offsets"):
        source_map.span(5, 4)


def test_snapshot_with_unknown_math_appends_without_mutating_original():
    document = doc("a.md", "Text $x$.\n")
    inline = InlineMathFact(
        fact_id="a.md::inline-math::6",
        document_id="a.md",
        span=None,
        raw="$x$",
        body="x",
        delimiter_kind="dollar",
        context="paragraph",
    )
    unknown = UnknownMathFact(
        fact_id="a.md::unknown-math::6",
        document_id="a.md",
        span=None,
        raw="$x$",
        source_math_fact_id=inline.fact_id,
        reason="macro",
        excerpt=r"\newcommand",
    )

    snapshot = FactSnapshot(documents=(document,), inline_math=(inline,))
    updated = snapshot.with_unknown_math((unknown,))

    assert snapshot.unknown_math == ()
    assert updated.inline_math == (inline,)
    assert updated.unknown_math == (unknown,)
    assert updated.all_facts() == (inline, unknown)


def test_query_host_views_expose_snapshot_contracts():
    document = doc("a.md", "Text\n")
    generated_document = doc("a.html", "<p>Text</p>\n")
    heading = HeadingFact(
        fact_id="heading-1",
        document_id="a.md",
        span=span(),
        raw="# Title",
        level=1,
        text="Title",
        slug_candidate="title",
    )
    section = SectionFact(
        fact_id="section-1",
        document_id="a.md",
        span=span(),
        heading_fact_id=heading.fact_id,
        parent_section_id=None,
        depth=1,
        ordinal_path=(1,),
    )
    fence = FenceFact(
        fact_id="fence-1",
        document_id="a.md",
        span=span(),
        opener="```",
        fence_char="`",
        fence_length=3,
        info_string="{python}",
        language="python",
        kind="code-cell",
        is_closed=False,
        opener_span=span(start=0, end=3),
        closer_span=None,
        body_span=span(start=4, end=8),
    )
    directive = DirectiveFact(
        fact_id="directive-1",
        document_id="a.md",
        span=span(),
        name="code-cell",
        argument="python",
        options=(("renderings", "html"), ("fig-cap", "Plot")),
        fence_fact_id=fence.fact_id,
    )
    cell = CodeCellFact(
        fact_id="cell-1",
        document_id="a.md",
        span=span(),
        fence_fact_id=fence.fact_id,
        directive_fact_id=directive.fact_id,
        language="python",
        engine="jupyter",
        options=directive.options,
        label="plot",
    )
    unlabeled_cell = CodeCellFact(
        fact_id="cell-unlabeled",
        document_id="a.md",
        span=span(),
        fence_fact_id=fence.fact_id,
        directive_fact_id=None,
        language="python",
        engine="jupyter",
        options=(),
        label=None,
    )
    non_crossref_cell = CodeCellFact(
        fact_id="cell-non-crossref",
        document_id="a.md",
        span=span(),
        fence_fact_id=fence.fact_id,
        directive_fact_id=None,
        language="python",
        engine="jupyter",
        options=(),
        label="plot-plain",
    )
    prefixed_cell = CodeCellFact(
        fact_id="cell-prefixed",
        document_id="a.md",
        span=span(),
        fence_fact_id=fence.fact_id,
        directive_fact_id=None,
        language="python",
        engine="jupyter",
        options=(),
        label="fig-plot",
    )
    source_anchor = TargetAnchorFact(
        fact_id="target-source",
        document_id="a.md",
        span=span(),
        label="Intro",
        normalized_label="intro",
        target_kind="heading",
        attaches_to_fact_id=heading.fact_id,
        placement="before_heading",
    )
    duplicate_anchor = TargetAnchorFact(
        fact_id="target-duplicate",
        document_id="a.md",
        span=span(),
        label="intro",
        normalized_label="intro",
        target_kind="heading",
        attaches_to_fact_id=heading.fact_id,
        placement="standalone",
    )
    orphaned_anchor = TargetAnchorFact(
        fact_id="target-orphaned",
        document_id="a.md",
        span=span(),
        label="Lonely",
        normalized_label="lonely",
        target_kind=None,
        attaches_to_fact_id=None,
        placement="orphaned",
    )
    ref = GenericRefFact(
        fact_id="ref-1",
        document_id="a.md",
        span=span(),
        role_kind="ref",
        target="Intro",
        normalized_target="intro",
    )
    unresolved_ref = GenericRefFact(
        fact_id="ref-missing",
        document_id="a.md",
        span=span(),
        role_kind="ref",
        target="Missing",
        normalized_target="missing",
    )
    equation = EquationLabelFact(
        fact_id="eq-label-1",
        document_id="a.md",
        span=span(),
        label="eq:energy",
        normalized_label="eq:energy",
        label_syntax_kind="myst",
        source_block_id="math-1",
    )
    equation_ref = EquationRefFact(
        fact_id="eq-ref-1",
        document_id="a.md",
        span=span(),
        raw="{eq}`eq:missing`",
        ref_kind="eq",
        target="eq:missing",
        normalized_target="eq:missing",
    )
    inline = InlineMathFact(
        fact_id="inline-1",
        document_id="a.md",
        span=span(),
        raw="$x$",
        body="x",
        delimiter_kind="dollar",
        context="paragraph",
    )
    display = DisplayMathFact(
        fact_id="display-1",
        document_id="a.md",
        span=span(),
        raw="$$x$$",
        body="x",
        container="dollar-dollar",
        label_fact_ids=("eq-1", "eq-2"),
    )
    unknown = UnknownMathFact(
        fact_id="unknown-1",
        document_id="a.md",
        span=span(),
        raw=r"\newcommand{\x}{x}",
        source_math_fact_id=display.fact_id,
        reason="macro",
        excerpt=r"\newcommand",
    )
    member = ProjectMemberFact(
        fact_id="member-1",
        document_id="a.md",
        span=None,
        path=PurePosixPath("a.md"),
        project_root=PurePosixPath("."),
        declared=True,
        discovered=True,
        normalized_path=PurePosixPath("chapter.md"),
    )
    duplicate_member = ProjectMemberFact(
        fact_id="member-2",
        document_id="b.md",
        span=None,
        path=PurePosixPath("./a.md"),
        project_root=PurePosixPath("."),
        declared=False,
        discovered=True,
        normalized_path=PurePosixPath("chapter.md"),
    )
    hidden = HiddenExcludedFact(
        fact_id="hidden-1",
        document_id=".secret.md",
        span=None,
        path=PurePosixPath(".secret.md"),
        reason="hidden",
    )
    excluded = HiddenExcludedFact(
        fact_id="excluded-1",
        document_id="build/out.md",
        span=None,
        path=PurePosixPath("build/out.md"),
        reason="excluded",
    )
    provenance = GeneratedProvenanceFact(
        fact_id="generated-1",
        document_id="a.html",
        span=None,
        generated_document_id="a.html",
        source_document_id="a.md",
        source_sha="abc123",
    )
    portability = OutputPortabilityFact(
        fact_id="portability-1",
        document_id="a.md",
        span=span(),
        subject_fact_id=cell.fact_id,
        output_profile="quarto-html",
        risk_kind="crossref-label",
    )
    syntax_issue = StructureSyntaxIssueFact(
        fact_id="syntax-1",
        document_id="a.md",
        span=span(),
        raw="{ref}target",
        kind="myst-role",
        reason="malformed MyST role syntax",
    )

    snapshot = FactSnapshot(
        documents=(document, generated_document),
        headings=(heading,),
        sections=(section,),
        fences=(fence,),
        directives=(directive,),
        code_cells=(cell, unlabeled_cell, non_crossref_cell, prefixed_cell),
        structure_syntax_issues=(syntax_issue,),
        target_anchors=(source_anchor, duplicate_anchor, orphaned_anchor),
        generic_refs=(ref, unresolved_ref),
        equation_labels=(equation,),
        equation_refs=(equation_ref,),
        inline_math=(inline,),
        display_math=(display,),
        unknown_math=(unknown,),
        project_members=(member, duplicate_member),
        hidden_excluded=(hidden, excluded),
        generated_provenance=(provenance,),
        portability=(portability,),
    )
    query = QueryHost(snapshot)

    assert query.structure.headings() == (heading,)
    assert query.structure.sections() == (section,)
    assert query.structure.fences() == (fence,)
    assert query.structure.directives() == (directive,)
    assert query.structure.code_cells() == (cell, unlabeled_cell, non_crossref_cell, prefixed_cell)
    assert query.structure.syntax_issues() == (syntax_issue,)
    assert query.structure.unclosed_fences() == (fence,)
    assert directive.option_dict() == {"renderings": "html", "fig-cap": "Plot"}
    assert cell.option_dict() == directive.option_dict()

    assert query.references.generic_targets() == (
        source_anchor,
        duplicate_anchor,
        orphaned_anchor,
    )
    assert query.references.equation_targets() == (equation,)
    assert query.references.visible_equation_targets() == (equation,)
    assert query.references.hidden_equation_targets() == ()
    assert query.references.excluded_equation_targets() == ()
    assert query.references.equation_refs() == (equation_ref,)
    assert query.references.generic_refs() == (ref, unresolved_ref)
    assert query.references.target_index()["intro"] == (source_anchor, duplicate_anchor)
    assert query.references.duplicate_generic_targets() == {
        "intro": (source_anchor, duplicate_anchor)
    }
    assert query.references.unresolved_generic_refs() == (unresolved_ref,)
    assert query.references.ambiguous_generic_refs() == (ref,)
    assert query.references.orphaned_targets() == (orphaned_anchor,)
    assert query.references.unresolved_equation_refs() == (equation_ref,)
    assert query.references.ambiguous_equation_refs() == ()

    assert query.math.inline_math() == (inline,)
    assert query.math.display_math() == (display,)
    assert query.math.unknown_math() == (unknown,)
    assert query.math.display_with_multiple_labels() == (display,)

    assert query.generated.provenance() == (provenance,)
    assert query.generated.generated_document_ids() == ("a.html",)
    assert query.generated.dropped_targets() == (
        (provenance, duplicate_anchor),
        (provenance, orphaned_anchor),
    )

    assert query.project.members() == (member, duplicate_member)
    assert query.project.hidden_files() == (hidden,)
    assert query.project.excluded_files() == (excluded,)
    assert query.project.duplicate_normalized_paths() == {
        PurePosixPath("chapter.md"): (member, duplicate_member)
    }

    assert query.portability.inline_math_missing_alt() == (inline,)
    assert query.portability.display_math_missing_alt() == (display,)
    assert query.portability.quarto_crossref_label_issues() == (cell,)
    assert query.portability.renderings_with_crossref_options() == (cell,)
    assert snapshot.all_facts()[-1] == portability


def test_diagnostic_ir_result_and_frontend_contracts_are_projected():
    class NoopEngine:
        name = "noop"
        rule_codes = frozenset({"STR001"})

        def run(self, query: QueryHost) -> tuple[DiagnosticIR, ...]:
            return ()

    document = doc("a.md", "Text\n")
    location = RelatedLocation(span=span(start=1, end=2), message="related")
    diagnostic_ir = DiagnosticIR(
        code="STR001",
        message="Heading marker must be followed by a space",
        span=span(),
        severity_default=Severity.WARNING,
        detail="The heading is parsed differently by downstream renderers.",
        hint="Add a space after the heading marker.",
        rule="heading-atx-space",
        related_locations=(location,),
    )

    diagnostic = diagnostic_ir.to_diagnostic(Severity.ERROR)
    snapshot = FactSnapshot(documents=(document,))
    result = AnalysisResult(
        snapshot=snapshot,
        diagnostics=(
            diagnostic,
            Diagnostic("REF001", Severity.WARNING, "missing target", None),
            Diagnostic("INF001", Severity.INFO, "note", None),
        ),
        profiles=("scientific-myst",),
    )
    document_ir = DocumentIR(document_id="a.md", document=document, facts=())
    frontend_result = FrontendResult(documents=(document_ir,))

    assert diagnostic.severity is Severity.ERROR
    assert diagnostic.detail == diagnostic_ir.detail
    assert diagnostic.hint == diagnostic_ir.hint
    assert diagnostic.rule == diagnostic_ir.rule
    assert diagnostic_ir.related_locations == (location,)
    assert result.schema_version == "0.2-architecture-preview"
    assert result.summary() == {
        "files_checked": 1,
        "facts": 0,
        "diagnostics": 3,
        "errors": 1,
        "warnings": 1,
        "info": 1,
    }
    assert frontend_result.documents == (document_ir,)
    assert engine_rule_codes(NoopEngine()) == frozenset({"STR001"})
