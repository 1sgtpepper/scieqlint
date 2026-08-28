from __future__ import annotations

import json
from importlib import resources
from pathlib import PurePosixPath

import pytest
from jsonschema.validators import Draft202012Validator
from referencing import Registry, Resource

from scieqlint.api import check_documents as public_check_documents
from scieqlint.app import _profile_snapshot, _source_reference_facts, check_documents
from scieqlint.config.model import (
    AlgebraConfig,
    ChecksConfig,
    Config,
    OutputProfile,
    ProfileConfig,
    ScannerConfig,
)
from scieqlint.diag.model import SourceSpan
from scieqlint.engine.portability import PortabilityEngine
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.policy import PolicyHost
from scieqlint.query.host import QueryHost
from scieqlint.report.json import JsonReporter
from scieqlint.report.sarif import SarifReporter
from scieqlint.scan.base import EquationReference, ReferenceSource


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("cross-format.md"),
        text,
        DocumentKind.MARKDOWN,
    )


def notebook_doc(text: str | list[str]) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("cross-format.ipynb"),
        json.dumps(
            {
                "cells": [
                    {"cell_type": "markdown", "metadata": {}, "source": text},
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        DocumentKind.NOTEBOOK,
    )


def config(output_profile: OutputProfile) -> Config:
    return Config(
        profile=ProfileConfig(
            name="cross-format-references",
            output_profile=output_profile,
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


def test_cross_format_profile_materializes_notebook_reference_risks() -> None:
    source = "$$\nx = 1\n$$ {#eq-one}\n\n{eq}`eq-one`\n\n{numref}`eq-one`\n"

    snapshot = _profile_snapshot((notebook_doc(source),), config("commonmark"))

    assert [fact.label for fact in snapshot.equation_labels] == ["eq-one"]
    assert [(fact.ref_kind, fact.target) for fact in snapshot.equation_refs] == [
        ("eq", "eq-one"),
        ("numref", "eq-one"),
    ]
    assert all(fact.span.cell == 0 for fact in (*snapshot.equation_labels, *snapshot.equation_refs))
    assert [dict(fact.metadata)["ref_kind"] for fact in snapshot.portability] == [
        "eq",
        "numref",
    ]


def test_public_profile_filters_non_source_references_before_materializing_facts() -> None:
    markdown = doc("$$\nx = 1\n$$ {#markdown-equation}\n\n{eq}`markdown-equation`\n")
    notebook = notebook_doc(
        "$$\nx = 1\n$$ {#notebook-equation}\n\n[ordinary](#section)\n\n{eq}`notebook-equation`\n"
    )

    result = public_check_documents(
        (markdown, notebook),
        config=config("commonmark"),
    )

    portability = tuple(item for item in result.diagnostics if item.code == "PORT001")
    assert [
        (dict(item.properties)["ref_kind"], item.span.path if item.span is not None else None)
        for item in portability
    ] == [
        ("eq", notebook.path),
        ("eq", markdown.path),
    ]


def test_cross_format_profile_ignores_caller_references_outside_included_sources() -> None:
    included = SourceDocument.from_text(
        PurePosixPath("included.tex"),
        "",
        DocumentKind.LATEX,
    )
    external = EquationReference(
        target="outside",
        span=SourceSpan(
            path=PurePosixPath("outside.tex"),
            start=0,
            end=7,
            line=1,
            col=1,
            end_line=1,
            end_col=8,
        ),
        raw=r"\ref{outside}",
        source=ReferenceSource.LATEX_REF,
    )

    assert (
        _source_reference_facts(
            (included,),
            (external,),
            config("commonmark"),
        )
        == ()
    )


def test_cross_format_profile_preserves_source_role_ownership_across_paths() -> None:
    markdown_path = PurePosixPath("same.md")
    markdown_source = "$$\nx=1\n$$ {#md}\n\n{eq}`tex`\n"
    markdown = SourceDocument.from_text(markdown_path, markdown_source, DocumentKind.MARKDOWN)
    latex = SourceDocument.from_text(
        PurePosixPath("source.tex"),
        "\\begin{equation}\ny=2 \\label{tex}\n\\end{equation}\n",
        DocumentKind.LATEX,
    )

    result = public_check_documents((markdown, latex), config=config("commonmark"))

    assert [item.code for item in result.diagnostics if item.code.startswith("REF")] == []
    portability = [item for item in result.diagnostics if item.code == "PORT001"]
    assert len(portability) == 1
    [diagnostic] = portability
    assert diagnostic.span is not None
    assert markdown_source[diagnostic.span.start : diagnostic.span.end] == "{eq}`tex`"
    assert dict(diagnostic.properties)["ref_kind"] == "eq"
    assert dict(diagnostic.properties)["target"] == "tex"


def test_cross_format_profile_keeps_one_reference_owner_when_markdown_scanning_is_disabled() -> (
    None
):
    source = (
        "\\begin{equation}\n"
        "x=1 \\label{duplicate}\n"
        "\\end{equation}\n"
        "\\begin{equation}\n"
        "y=2 \\label{duplicate}\n"
        "\\end{equation}\n"
    )
    document = SourceDocument.from_text(
        PurePosixPath("duplicate.tex"),
        source,
        DocumentKind.LATEX,
    )
    profile_config = Config(
        profile=ProfileConfig(
            name="cross-format-references",
            output_profile="commonmark",
        ),
        scanner=ScannerConfig(markdown=False),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
    )

    result = public_check_documents((document,), config=profile_config)

    duplicates = [diagnostic for diagnostic in result.diagnostics if diagnostic.code == "REF001"]
    assert len(duplicates) == 1
    [diagnostic] = duplicates
    assert diagnostic.message == "duplicate equation label: duplicate"
    assert diagnostic.span is not None
    assert diagnostic.span.path == PurePosixPath("duplicate.tex")
    assert source[diagnostic.span.start : diagnostic.span.end] == "duplicate"


def test_cross_format_profile_rejects_duplicate_document_paths() -> None:
    duplicate = doc("See {eq}`same`.\n")

    with pytest.raises(ValueError, match=r"^duplicate document path\(s\): cross-format\.md$"):
        check_documents((duplicate, duplicate), config=config("commonmark"))


def test_cross_format_profile_rejects_duplicate_paths_across_document_kinds() -> None:
    path = PurePosixPath("same.md")
    markdown = SourceDocument.from_text(path, "See {eq}`tex`.\n", DocumentKind.MARKDOWN)
    latex = SourceDocument.from_text(
        path,
        "\\begin{equation}\ny=2 \\label{tex}\n\\end{equation}\n",
        DocumentKind.LATEX,
    )

    with pytest.raises(ValueError, match=r"^duplicate document path\(s\): same\.md$"):
        check_documents((markdown, latex), config=config("commonmark"))


def test_check_documents_maps_same_notebook_targets_to_exact_source_spans_and_ids() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("same.ipynb"),
        json.dumps(
            {
                "cells": [
                    {"cell_type": "markdown", "metadata": {}, "source": "{eq}`same`"},
                    {"cell_type": "markdown", "metadata": {}, "source": "{eq}`same`"},
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        DocumentKind.NOTEBOOK,
    )

    result = check_documents((document,), config=config("commonmark"))

    portability = tuple(item for item in result.diagnostics if item.code == "PORT001")
    spans = tuple(item.span for item in portability)
    assert all(span is not None for span in spans)
    marker = "{eq}`same`"
    first_start = document.text.index(marker)
    second_start = document.text.index(marker, first_start + len(marker))
    assert [(span.cell, span.start, span.end) for span in spans if span is not None] == [
        (0, first_start, first_start + len(marker)),
        (1, second_start, second_start + len(marker)),
    ]
    assert [document.text[span.start : span.end] for span in spans if span is not None] == [
        marker,
        marker,
    ]
    assert [dict(item.properties)["subject_fact_id"] for item in portability] == [
        "same.ipynb::notebook-cell::0::same.ipynb::eq-ref::5",
        "same.ipynb::notebook-cell::1::same.ipynb::eq-ref::5",
    ]
    assert len({dict(item.properties)["subject_fact_id"] for item in portability}) == 2
    assert all(span.segments for span in spans if span is not None)


def test_public_loaded_documents_keep_source_role_fact_ids_collision_free() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("same.ipynb"),
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": "1234567{eq}`same` {eq}`same`",
                    },
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": "1234567{eq}`same`",
                    },
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        DocumentKind.NOTEBOOK,
    )
    collision_twin = SourceDocument.from_text(
        PurePosixPath("same.ipynb::cell-0"),
        "12345\\eqref{same}",
        DocumentKind.LATEX,
    )

    result = public_check_documents(
        (document, collision_twin),
        config=config("commonmark"),
    )

    portability = tuple(item for item in result.diagnostics if item.code == "PORT001")
    assert len(portability) == 4
    owner_occurrences: dict[tuple[PurePosixPath, int | None], list[str]] = {}
    for item in portability:
        assert item.span is not None
        owner = (item.span.path, item.span.cell)
        owner_occurrences.setdefault(owner, []).append(dict(item.properties)["subject_fact_id"])

    assert {
        (path, cell, len(subject_ids)) for (path, cell), subject_ids in owner_occurrences.items()
    } == {
        (document.path, 0, 2),
        (document.path, 1, 1),
        (collision_twin.path, None, 1),
    }
    subject_ids = [
        subject_id
        for owner_subject_ids in owner_occurrences.values()
        for subject_id in owner_subject_ids
    ]
    assert len(subject_ids) == 4
    assert len(set(subject_ids)) == 4
    assert (
        owner_occurrences[(document.path, 0)][0]
        != owner_occurrences[(collision_twin.path, None)][0]
    )


@pytest.mark.public_regression
def test_public_cross_format_notebook_role_emits_one_portability_diagnostic() -> None:
    source = "$$\nx = 1\n$$ {#eq-one}\n\n{eq}`eq-one`\n"
    document = notebook_doc(source)

    result = check_documents((document,), config=config("commonmark"))

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["PORT001"]
    [diagnostic] = result.diagnostics
    assert diagnostic.profile == "cross-format-references"
    assert diagnostic.span is not None
    assert diagnostic.span.cell == 0
    assert document.text[diagnostic.span.start : diagnostic.span.end] == "{eq}`eq-one`"


@pytest.mark.public_regression
def test_public_cross_format_notebook_split_generic_ref_keeps_exact_target_span() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("cross-format.ipynb"),
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": ["See {", "ref}`missing`.\n"],
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        DocumentKind.NOTEBOOK,
    )

    result = check_documents((document,), config=config("commonmark"))

    assert result.files_checked == 1
    assert result.math_blocks_checked == 0
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["REF004"]
    [diagnostic] = result.diagnostics
    assert diagnostic.detail == "reference text: {ref}`missing`"
    assert diagnostic.span is not None
    assert diagnostic.span.path == document.path
    assert diagnostic.span.cell == 0
    assert diagnostic.span.segments
    assert document.text[diagnostic.span.start : diagnostic.span.end] == "missing"


@pytest.mark.public_regression
def test_public_cross_format_notebook_raw_equation_preserves_json_owned_facts() -> None:
    source = (
        r"\begin{equation}"
        "\n"
        r"x = 1 \label{eq-raw} \eqref{eq-raw}"
        "\n"
        r"\end{equation}"
    )
    document = notebook_doc(source)
    snapshot = _profile_snapshot((document,), config("commonmark"))

    assert len(snapshot.display_math) == 1
    assert len(snapshot.equation_labels) == 1
    assert len(snapshot.equation_refs) == 1
    assert len(snapshot.crossref_metadata) == 2
    assert len(snapshot.portability) == 1

    [display] = snapshot.display_math
    [label] = snapshot.equation_labels
    [reference] = snapshot.equation_refs
    assert display.container == "ams"
    assert display.span is not None
    assert display.span.cell == 0
    assert display.span.cell_line == 1
    assert document.text[display.span.start : display.span.end] == json.dumps(source)[1:-1]
    assert label.label == "eq-raw"
    assert label.span is not None
    assert label.span.cell == 0
    assert label.span.cell_line == 2
    assert label.label_span is not None
    assert label.label_span.cell == 0
    assert label.label_span.cell_line == 2
    assert document.text[label.label_span.start : label.label_span.end] == "eq-raw"
    assert reference.ref_kind == "tex-eqref"
    assert reference.target == "eq-raw"
    assert reference.span is not None
    assert reference.span.cell == 0
    assert reference.span.cell_line == 2
    assert reference.role_span is not None
    assert reference.role_span.cell == 0
    assert reference.role_span.cell_line == 2
    assert (
        document.text[reference.role_span.start : reference.role_span.end]
        == json.dumps(r"\eqref{eq-raw}")[1:-1]
    )
    assert reference.target_span is not None
    assert reference.target_span.cell == 0
    assert reference.target_span.cell_line == 2
    assert document.text[reference.target_span.start : reference.target_span.end] == "eq-raw"
    assert [(fact.metadata_kind, fact.logical_target) for fact in snapshot.crossref_metadata] == [
        ("target-definition", "eq-raw"),
        ("reference-use", "eq-raw"),
    ]

    result = check_documents((document,), config=config("commonmark"))

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["PORT001"]
    [diagnostic] = result.diagnostics
    assert diagnostic.span is not None
    assert diagnostic.span.cell == 0
    assert (
        document.text[diagnostic.span.start : diagnostic.span.end]
        == json.dumps(r"\eqref{eq-raw}")[1:-1]
    )


def test_notebook_raw_equation_ids_are_stable_across_json_formatting() -> None:
    source = [
        r"\begin{equation}" + "\r",
        "\n" + r"x = 1 \label{eq-split} ",
        r"\eqref{eq-split}" + "\n" + r"\end{equation}",
    ]
    payload = {
        "cells": [{"cell_type": "markdown", "metadata": {}, "source": source}],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    documents = tuple(
        SourceDocument.from_text(
            PurePosixPath("stable.ipynb"),
            json.dumps(payload, **options),
            DocumentKind.NOTEBOOK,
        )
        for options in ({}, {"indent": 2})
    )

    identities: list[tuple[str, str, str]] = []
    for document in documents:
        snapshot = _profile_snapshot((document,), config("commonmark"))
        [display] = snapshot.display_math
        [label] = snapshot.equation_labels
        [reference] = snapshot.equation_refs
        assert display.span is not None
        assert any(len(segment.ranges) == 2 for segment in display.span.segments)
        assert label.label_span is not None
        assert label.label_span.cell == 0
        assert label.label_span.segments
        assert [
            document.text[start:end]
            for segment in label.label_span.segments
            for start, end in segment.ranges
        ] == list("eq-split")
        assert reference.role_span is not None
        assert reference.role_span.cell == 0
        assert reference.role_span.segments
        identities.append((display.fact_id, label.fact_id, reference.fact_id))

    assert identities[0] == identities[1]


def test_reference_portability_matrix_is_conservative_and_explicit() -> None:
    document = doc(_SOURCE)

    commonmark = _profile_snapshot((document,), config("commonmark"))
    notebook = _profile_snapshot((document,), config("notebook"))
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


def test_portability_engine_consumes_facts_without_reading_source_text() -> None:
    snapshot = _profile_snapshot((doc(_SOURCE),), config("commonmark"))
    query = QueryHost(snapshot)
    diagnostics = PortabilityEngine(
        profile="cross-format-references",
        policy=PolicyHost(output_profile="commonmark"),
    ).run(query)

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
        .joinpath("scieqlint-result-0.2.schema.json")
        .read_text()
    )
    diagnostic_schema = json.loads(
        resources.files("scieqlint.schemas")
        .joinpath("scieqlint-diagnostic-0.2.schema.json")
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
        PolicyHost().cross_format_reference_risks(snapshot, "pdf")

    with pytest.raises(ValueError, match=r"^unsupported output profile: $"):
        PolicyHost(output_profile="myst").cross_format_reference_risks(snapshot, "")
