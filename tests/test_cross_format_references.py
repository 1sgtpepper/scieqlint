from __future__ import annotations

import json
from importlib import resources
from pathlib import PurePosixPath
from typing import cast

import pytest
from jsonschema.validators import Draft202012Validator
from referencing import Registry, Resource

from scieqlint.api import check_documents as public_check_documents
from scieqlint.app import _profile_snapshot, check_documents
from scieqlint.config.model import (
    AlgebraConfig,
    ChecksConfig,
    Config,
    OutputProfile,
    ProfileConfig,
    ProfileSeverity,
)
from scieqlint.diag.model import Severity
from scieqlint.engine.portability import PortabilityEngine
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.policy import PolicyHost
from scieqlint.query.host import QueryHost
from scieqlint.report.json import JsonReporter
from scieqlint.report.sarif import SarifReporter


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("cross-format.md"),
        text,
        DocumentKind.MARKDOWN,
    )


def notebook_doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("cross-format.ipynb"),
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": text,
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            sort_keys=True,
        ),
        DocumentKind.NOTEBOOK,
    )


def latex_doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("cross-format.tex"),
        text,
        DocumentKind.LATEX,
    )


def config(
    output_profile: OutputProfile,
    *,
    severity: ProfileSeverity | None = None,
) -> Config:
    return Config(
        profile=ProfileConfig(
            name="cross-format-references",
            output_profile=output_profile,
            severity=severity,
        ),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
    )


_SOURCE = r"""$$
x = 1
$$ {#eq-one}

{eq}`eq-one`

$$
\begin{align}
y &= x \eqref{eq-one}
\end{align}
$$
"""


def test_cross_format_profile_materializes_source_spanned_reference_risks() -> None:
    document = doc(_SOURCE)
    snapshot = _profile_snapshot((document,), config("commonmark"))

    assert [(fact.risk_kind, fact.output_profile) for fact in snapshot.portability] == [
        ("equation-reference-syntax", "commonmark"),
        ("equation-reference-syntax", "commonmark"),
    ]
    assert [dict(fact.metadata) for fact in snapshot.portability] == [
        {"ref_kind": "eq", "target": "eq-one"},
        {"ref_kind": "tex-eqref", "target": "eq-one"},
    ]
    assert [
        _SOURCE[fact.span.start : fact.span.end]
        for fact in snapshot.portability
        if fact.span is not None
    ] == ["{eq}`eq-one`", r"\eqref{eq-one}"]


def test_reference_portability_matrix_is_conservative_and_explicit() -> None:
    document = doc(_SOURCE)

    commonmark = _profile_snapshot((document,), config("commonmark"))
    notebook = _profile_snapshot((notebook_doc(_SOURCE),), config("notebook"))
    myst = _profile_snapshot((document,), config("myst"))
    typst = _profile_snapshot((document,), config("typst"))

    assert [dict(fact.metadata)["ref_kind"] for fact in commonmark.portability] == [
        "eq",
        "tex-eqref",
    ]
    assert [dict(fact.metadata)["ref_kind"] for fact in notebook.portability] == [
        "eq",
        "tex-eqref",
    ]
    assert myst.portability == ()
    assert [dict(fact.metadata)["ref_kind"] for fact in typst.portability] == ["tex-eqref"]


def test_notebook_source_references_reach_cross_format_policy() -> None:
    result = public_check_documents((notebook_doc(_SOURCE),), config=config("commonmark"))

    portability = [item for item in result.diagnostics if item.code == "PORT001"]
    assert len(portability) == 2
    assert all(item.span is not None and item.span.cell == 0 for item in portability)
    assert not any(item.code.startswith("REF") for item in result.diagnostics)
    assert [dict(item.properties)["ref_kind"] for item in portability] == [
        "eq",
        "tex-eqref",
    ]


def test_raw_latex_source_references_reach_cross_format_policy() -> None:
    source = r"""\begin{equation}
x = 1 \label{eq-one}
\end{equation}
See \eqref{eq-one}.
"""

    result = public_check_documents((latex_doc(source),), config=config("commonmark"))

    portability = [item for item in result.diagnostics if item.code == "PORT001"]
    assert len(portability) == 1
    assert portability[0].span is not None
    assert portability[0].span.path == PurePosixPath("cross-format.tex")
    assert dict(portability[0].properties)["ref_kind"] == "tex-eqref"
    assert not any(item.code.startswith("REF") for item in result.diagnostics)


def test_cross_format_notebook_errors_remain_deterministic() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("broken.ipynb"),
        "{",
        DocumentKind.NOTEBOOK,
    )

    result = public_check_documents((document,), config=config("commonmark"))

    assert [item.code for item in result.diagnostics] == ["INP001"]


@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        ("warning", Severity.WARNING),
        ("error", Severity.ERROR),
        ("disabled", None),
    ],
)
def test_policy_host_owns_profile_severity_and_disabled_behavior(
    severity: ProfileSeverity,
    expected: Severity | None,
) -> None:
    result = check_documents(
        (doc(_SOURCE),),
        config("commonmark", severity=severity),
    )
    diagnostics = [item for item in result.diagnostics if item.code == "PORT001"]

    if expected is None:
        assert diagnostics == []
    else:
        assert diagnostics
        assert all(item.severity is expected for item in diagnostics)


def test_portability_engine_consumes_facts_without_reading_source_text() -> None:
    snapshot = _profile_snapshot((doc(_SOURCE),), config("commonmark"))
    query = QueryHost(snapshot)
    diagnostics = PortabilityEngine(profile="cross-format-references").run(query)

    assert query.portability.risks() == snapshot.portability
    assert query.portability.risks("equation-reference-syntax") == snapshot.portability
    assert [(item.code, item.profile) for item in diagnostics] == [
        ("PORT001", "cross-format-references"),
        ("PORT001", "cross-format-references"),
    ]
    assert [dict(item.properties) for item in diagnostics] == [
        {
            "output_profile": "commonmark",
            "ref_kind": "eq",
            "target": "eq-one",
            "subject_fact_id": snapshot.equation_refs[0].fact_id,
        },
        {
            "output_profile": "commonmark",
            "ref_kind": "tex-eqref",
            "target": "eq-one",
            "subject_fact_id": snapshot.equation_refs[1].fact_id,
        },
    ]


def test_cross_format_profile_is_opt_in_and_preserves_reference_diagnostics() -> None:
    document = doc(_SOURCE)

    default = check_documents(
        (document,),
        config=Config(checks=ChecksConfig(algebra=AlgebraConfig(enabled=False))),
    )
    profiled = check_documents((document,), config=config("commonmark"))

    assert not any(item.code.startswith("PORT") for item in default.diagnostics)
    assert [item.code for item in profiled.diagnostics if item.code.startswith("REF")] == []
    assert [item.code for item in profiled.diagnostics if item.code.startswith("PORT")] == [
        "PORT001",
        "PORT001",
    ]


def test_json_and_sarif_project_profile_and_output_metadata() -> None:
    result = check_documents((doc(_SOURCE),), config=config("typst"))

    rendered_json = JsonReporter().render(result)
    json_result = json.loads(rendered_json)
    result_schema = json.loads(
        resources.files("scieqlint.schemas")
        .joinpath("scieqlint-result-0.1.schema.json")
        .read_text()
    )
    diagnostic_schema = json.loads(
        resources.files("scieqlint.schemas")
        .joinpath("scieqlint-diagnostic-0.1.schema.json")
        .read_text()
    )
    registry = Registry().with_resources(
        [
            (result_schema["$id"], Resource.from_contents(result_schema)),
            (diagnostic_schema["$id"], Resource.from_contents(diagnostic_schema)),
        ]
    )
    Draft202012Validator(result_schema, registry=registry).validate(json_result)
    [json_diagnostic] = [item for item in json_result["diagnostics"] if item["code"] == "PORT001"]
    assert json_diagnostic["profile"] == "cross-format-references"
    assert json_diagnostic["properties"]["output_profile"] == "typst"
    assert json_diagnostic["properties"]["ref_kind"] == "tex-eqref"

    sarif = json.loads(SarifReporter().render(result))
    [sarif_result] = [item for item in sarif["runs"][0]["results"] if item["ruleId"] == "PORT001"]
    assert sarif_result["properties"]["profile"] == "cross-format-references"
    assert sarif_result["properties"]["output_profile"] == "typst"
    assert sarif_result["properties"]["ref_kind"] == "tex-eqref"


def test_malformed_and_code_owned_reference_text_do_not_create_risks() -> None:
    source = r"""`{eq}`missing`` and `{eq}`missing` and \eqref{}

```tex
\eqref{code-only}
```
"""
    snapshot = _profile_snapshot((doc(source),), config("commonmark"))

    assert snapshot.equation_refs == ()
    assert snapshot.portability == ()


def test_portability_facts_are_stable_after_newline_normalization() -> None:
    lf = _profile_snapshot((doc(_SOURCE),), config("commonmark"))
    crlf = _profile_snapshot((doc(_SOURCE.replace("\n", "\r\n")),), config("commonmark"))

    assert lf.equation_refs == crlf.equation_refs
    assert lf.portability == crlf.portability


def test_frontend_without_profile_does_not_materialize_portability_policy() -> None:
    snapshot = MySTFrontend().lower((doc(_SOURCE),))

    assert snapshot.equation_refs
    assert snapshot.portability == ()


def test_manual_cross_format_profile_without_target_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="profile.output_profile is required"):
        ProfileConfig(name="cross-format-references")


def test_policy_rejects_missing_and_unknown_output_profiles() -> None:
    snapshot = FactSnapshot()

    with pytest.raises(ValueError, match="requires an output profile"):
        PolicyHost().cross_format_reference_risks(snapshot)

    with pytest.raises(ValueError, match="unsupported output profile: pdf"):
        PolicyHost(
            ProfileConfig(
                name="cross-format-references",
                output_profile=cast(OutputProfile, "pdf"),
            )
        ).cross_format_reference_risks(snapshot)
