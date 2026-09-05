from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from importlib import resources
from pathlib import Path, PurePosixPath
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
    ProfileConfig,
    ScannerConfig,
)
from scieqlint.engine.portability import PortabilityEngine
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.policy import PolicyHost
from scieqlint.query.host import QueryHost
from scieqlint.report.json import JsonReporter
from scieqlint.report.sarif import SarifReporter


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("accessible-math.md"),
        text,
        DocumentKind.MARKDOWN,
    )


def notebook_doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("accessible-math.ipynb"),
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


def accessibility_config() -> Config:
    return Config(
        profile=ProfileConfig(name="math-accessibility"),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
    )


def test_accessibility_profile_tracks_only_explicit_inline_math_without_alt() -> None:
    source = r"""Paragraph $x$.

# Heading with {math}`y + 1`

- Item with \(z\)

Inferred text x = y; it is not an owned inline-math container.

`$code$`
"""
    snapshot = _profile_snapshot((doc(source),), accessibility_config())

    assert [fact.delimiter_kind for fact in snapshot.inline_math] == [
        "dollar",
        "myst-role",
        "latex-paren",
        "plain-text",
    ]
    missing = QueryHost(snapshot).portability.inline_math_missing_alt()
    assert [fact.surrounding_text_role for fact in missing] == [
        "paragraph",
        "heading",
        "list-item",
    ]
    assert [
        source[fact.span.start : fact.span.end] for fact in missing if fact.span is not None
    ] == ["x", "y + 1", "z"]
    assert snapshot.portability == ()


def test_accessible_inline_math_fact_is_not_reported_missing() -> None:
    source_snapshot = MySTFrontend().lower((doc("Use $x$ here.\n"),))
    [inline] = source_snapshot.inline_math
    accessible = replace(inline, alt="the variable x")
    snapshot = replace(source_snapshot, inline_math=(accessible,))

    assert QueryHost(snapshot).portability.inline_math_missing_alt() == ()


def test_public_api_projects_caller_owned_accessibility_metadata() -> None:
    document = doc("Use $x$ here.\n")
    [inline] = MySTFrontend().lower((document,)).inline_math
    assert inline.accessibility_id is not None

    result = public_check_documents(
        (document,),
        config=accessibility_config(),
        accessibility_metadata={inline.accessibility_id: "the variable x"},
    )

    assert result.diagnostics == ()


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({"": "accessible text"}, "accessibility_metadata keys must be non-empty strings"),
        ({1: "accessible text"}, "accessibility_metadata keys must be non-empty strings"),
        ({"known-id": 1}, "accessibility_metadata values must be strings"),
        (["known-id", "accessible text"], "accessibility_metadata must be a mapping"),
    ],
)
def test_public_api_rejects_malformed_accessibility_metadata(
    metadata: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        public_check_documents(
            (doc("Use $x$ here.\n"),),
            config=accessibility_config(),
            accessibility_metadata=cast(Mapping[str, str], metadata),
        )


def test_public_api_rejects_nonempty_accessibility_metadata_outside_its_profile() -> None:
    document = doc("Use $x$ here.\n")
    [inline] = MySTFrontend().lower((document,)).inline_math
    assert inline.accessibility_id is not None

    with pytest.raises(
        ValueError,
        match=r'accessibility_metadata requires profile\.name = "math-accessibility"',
    ):
        public_check_documents(
            (document,),
            config=Config(checks=ChecksConfig(algebra=AlgebraConfig(enabled=False))),
            accessibility_metadata={inline.accessibility_id: "the variable x"},
        )


def test_public_api_empty_accessibility_metadata_keeps_non_math_profiles_compatible() -> None:
    result = public_check_documents(
        (doc("Ordinary prose remains unchanged.\n"),),
        config=Config(checks=ChecksConfig(algebra=AlgebraConfig(enabled=False))),
        accessibility_metadata={},
    )

    assert result.diagnostics == ()


def test_public_api_rejects_accessibility_metadata_for_unknown_accessibility_ids() -> None:
    with pytest.raises(ValueError, match="unknown inline math fact"):
        public_check_documents(
            (doc("Use $x$ here.\n"),),
            config=accessibility_config(),
            accessibility_metadata={"unknown-inline-id": "not a source-owned ID"},
        )


def test_inferred_plain_text_candidates_cannot_accept_accessibility_metadata() -> None:
    document = doc("An inferred candidate x = y; stays plain text.\n")
    snapshot = MySTFrontend().lower((document,))
    [plain] = [fact for fact in snapshot.inline_math if fact.delimiter_kind == "plain-text"]
    assert plain.accessibility_id is None

    with pytest.raises(ValueError, match="unknown inline math fact"):
        public_check_documents(
            (document,),
            config=accessibility_config(),
            accessibility_metadata={plain.fact_id: "an equation"},
        )


def test_accessibility_metadata_owner_rejects_ambiguous_fact_ids() -> None:
    document = doc("Use $x$ here.\n")
    frontend_snapshot = MySTFrontend().lower((document,))
    [inline] = frontend_snapshot.inline_math
    assert inline.accessibility_id is not None
    duplicate = replace(inline, fact_id=f"{inline.fact_id}::duplicate")

    with pytest.raises(
        ValueError,
        match=r"ambiguous inline math fact\(s\): accessible-math\.md::inline-math::dollar::x",
    ):
        _profile_snapshot(
            (document,),
            accessibility_config(),
            frontend_snapshot=replace(
                frontend_snapshot,
                inline_math=(inline, duplicate),
            ),
            accessibility_metadata={inline.accessibility_id: "the variable x"},
        )


def test_public_api_rejects_unknown_accessibility_ids_when_markdown_scanning_is_disabled() -> None:
    with pytest.raises(ValueError, match="unknown inline math fact"):
        public_check_documents(
            (doc("Use $x$ here.\n"),),
            config=Config(
                profile=ProfileConfig(name="math-accessibility"),
                scanner=ScannerConfig(markdown=False),
                checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
            ),
            accessibility_metadata={"unknown-inline-id": "not a source-owned ID"},
        )


def test_public_api_rejects_unknown_accessibility_ids_for_unsupported_documents() -> None:
    unsupported = SourceDocument.from_text(
        PurePosixPath("unsupported.txt"),
        "plain text\n",
        DocumentKind.UNKNOWN,
    )

    with pytest.raises(ValueError, match="unknown inline math fact"):
        public_check_documents(
            (unsupported,),
            config=accessibility_config(),
            accessibility_metadata={"unknown-inline-id": "not a source-owned ID"},
        )


def test_math_accessibility_profile_covers_notebook_markdown_but_not_latex() -> None:
    result = public_check_documents(
        (
            notebook_doc("Notebook $x$ is covered by this profile.\n"),
            SourceDocument.from_text(
                PurePosixPath("accessible-math.tex"),
                r"LaTeX $x$ is intentionally outside this profile.",
                DocumentKind.LATEX,
            ),
        ),
        config=accessibility_config(),
    )

    assert result.files_checked == 2
    [diagnostic] = [item for item in result.diagnostics if item.code == "PORT002"]
    assert diagnostic.span is not None
    assert diagnostic.span.path == PurePosixPath("accessible-math.ipynb")
    assert diagnostic.span.cell == 0


def test_cross_format_profile_does_not_enable_accessibility_rule() -> None:
    result = public_check_documents(
        (doc("Use $x$ here.\n"),),
        config=Config(
            profile=ProfileConfig(
                name="cross-format-references",
                output_profile="commonmark",
            ),
            checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
        ),
    )

    assert not any(item.code == "PORT002" for item in result.diagnostics)


def test_ordinary_markdown_accessibility_ids_keep_the_documented_format() -> None:
    snapshot = MySTFrontend().lower((doc("Use $x$ and $x$.\n"),))

    assert [fact.accessibility_id for fact in snapshot.inline_math] == [
        "accessible-math.md::inline-math::dollar::x",
        "accessible-math.md::inline-math::dollar::x::1",
    ]


def test_accessibility_engine_emits_fact_backed_metadata_in_source_order() -> None:
    source = "Use $x$ and {math}`y`.\n"
    snapshot = _profile_snapshot((doc(source),), accessibility_config())
    diagnostics = PortabilityEngine(
        profile="math-accessibility",
        policy=PolicyHost(),
    ).run(QueryHost(snapshot))

    assert [(item.code, item.profile) for item in diagnostics] == [
        ("PORT002", "math-accessibility"),
        ("PORT002", "math-accessibility"),
    ]
    assert [dict(item.properties)["delimiter_kind"] for item in diagnostics] == [
        "dollar",
        "myst-role",
    ]
    assert all(
        dict(item.properties)["accessibility_requirement"] == "accessible-text"
        for item in diagnostics
    )
    assert [dict(item.properties)["accessibility_id"] for item in diagnostics] == [
        fact.accessibility_id
        for fact in snapshot.inline_math
        if fact.delimiter_kind != "plain-text"
    ]


def test_accessibility_profile_is_opt_in_and_non_math_text_stays_quiet() -> None:
    document = doc("Inline $x$ and prose without math.\n")
    no_math = doc("Only prose, punctuation, and `code`.\n")
    default = check_documents(
        (document,),
        config=Config(checks=ChecksConfig(algebra=AlgebraConfig(enabled=False))),
    )
    profiled = check_documents((document,), config=accessibility_config())
    non_math = check_documents((no_math,), config=accessibility_config())

    assert not any(item.code == "PORT002" for item in default.diagnostics)
    assert [item.code for item in profiled.diagnostics if item.code == "PORT002"] == ["PORT002"]
    assert not any(item.code == "PORT002" for item in non_math.diagnostics)


def test_check_documents_accepts_direct_profile_config() -> None:
    result = public_check_documents(
        (doc("Inline $x$ math.\n"),),
        config=Config(
            scanner=ScannerConfig(inline_math=True),
            profile=ProfileConfig(name="math-accessibility"),
        ),
    )

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["PORT002"]


def test_unsupported_inline_environment_keeps_accessibility_span_and_status() -> None:
    source = r"Before {math}`\begin{cases}x\end{cases}` after."
    snapshot = _profile_snapshot((doc(source),), accessibility_config())
    [inline] = QueryHost(snapshot).portability.inline_math_missing_alt()
    [diagnostic] = PortabilityEngine(
        profile="math-accessibility",
        policy=PolicyHost(),
    ).run(QueryHost(snapshot))

    assert inline.parse_status == "unsupported"
    assert inline.span is not None
    assert source[inline.span.start : inline.span.end] == r"\begin{cases}x\end{cases}"
    assert dict(diagnostic.properties)["parse_status"] == "unsupported"


def test_accessibility_json_and_sarif_outputs_do_not_rescan_source() -> None:
    result = check_documents((doc("Use $x$.\n"),), config=accessibility_config())

    json_payload = json.loads(JsonReporter().render(result))
    [json_diagnostic] = [item for item in json_payload["diagnostics"] if item["code"] == "PORT002"]
    assert json_diagnostic["profile"] == "math-accessibility"
    assert json_diagnostic["properties"]["delimiter_kind"] == "dollar"
    assert json_diagnostic["properties"]["surrounding_text_role"] == "paragraph"

    sarif_payload = json.loads(SarifReporter().render(result))
    [sarif_result] = [
        item for item in sarif_payload["runs"][0]["results"] if item["ruleId"] == "PORT002"
    ]
    assert sarif_result["properties"]["profile"] == "math-accessibility"
    assert sarif_result["properties"]["accessibility_requirement"] == "accessible-text"
    assert sarif_result["properties"]["accessibility_id"] == (
        "accessible-math.md::inline-math::dollar::x"
    )


def test_accessibility_facts_are_deterministic_after_newline_normalization() -> None:
    source = "One $x$.\n\n- Two {math}`y`.\n"
    lf = _profile_snapshot((doc(source),), accessibility_config())
    crlf = _profile_snapshot(
        (doc(source.replace("\n", "\r\n")),),
        accessibility_config(),
    )

    assert lf.inline_math == crlf.inline_math
    assert lf.portability == crlf.portability
    assert (
        QueryHost(lf).portability.inline_math_missing_alt()
        == QueryHost(crlf).portability.inline_math_missing_alt()
    )


def test_inline_math_at_eof_keeps_exact_accessibility_span() -> None:
    source = "Ends with $x + y$"
    snapshot = _profile_snapshot((doc(source),), accessibility_config())
    [inline] = QueryHost(snapshot).portability.inline_math_missing_alt()

    assert inline.span is not None
    assert source[inline.span.start : inline.span.end] == "x + y"


def _accessibility_fixture_result():
    path = Path("tests/fixtures/good/inline_math_accessibility.md")
    document = SourceDocument.from_text(
        PurePosixPath(path.as_posix()),
        path.read_text(encoding="utf-8"),
        DocumentKind.MARKDOWN,
    )
    return public_check_documents((document,), config=accessibility_config())


def test_accessibility_json_golden_output_is_stable() -> None:
    expected = Path("tests/golden/json/inline_math_accessibility.json").read_text(encoding="utf-8")

    assert JsonReporter().render(_accessibility_fixture_result()) == expected


def test_accessibility_sarif_golden_output_is_stable() -> None:
    expected = Path("tests/golden/sarif/inline_math_accessibility.sarif").read_text(
        encoding="utf-8"
    )

    assert SarifReporter().render(_accessibility_fixture_result()) == expected


def test_accessibility_json_output_validates_against_packaged_schema() -> None:
    result_schema = json.loads(
        resources.files("scieqlint.schemas")
        .joinpath("scieqlint-result-0.2.schema.json")
        .read_text(encoding="utf-8")
    )
    diagnostic_schema = json.loads(
        resources.files("scieqlint.schemas")
        .joinpath("scieqlint-diagnostic-0.2.schema.json")
        .read_text(encoding="utf-8")
    )
    registry = Registry().with_resources(
        [
            (result_schema["$id"], Resource.from_contents(result_schema)),
            (diagnostic_schema["$id"], Resource.from_contents(diagnostic_schema)),
        ]
    )
    payload = json.loads(JsonReporter().render(_accessibility_fixture_result()))

    Draft202012Validator(result_schema, registry=registry).validate(payload)
    assert (
        diagnostic_schema["properties"]["properties"]["properties"]["accessibility_id"]["type"]
        == "string"
    )


def test_portability_engine_rejects_unknown_profile() -> None:
    with pytest.raises(ValueError, match="unsupported portability profile: future"):
        PortabilityEngine(
            profile="future",
            policy=PolicyHost(),
        ).run(QueryHost(FactSnapshot()))


def test_portability_engine_rejects_unowned_risk_kinds() -> None:
    unknown = OutputPortabilityFact(
        fact_id="unknown-risk",
        document_id="accessible-math.md",
        span=None,
        subject_fact_id="subject",
        output_profile="unknown",
        risk_kind="future-risk",
    )
    snapshot = FactSnapshot(portability=(unknown,))

    with pytest.raises(ValueError, match="unsupported portability risk kind: future-risk"):
        PortabilityEngine(
            profile="cross-format-references",
            policy=PolicyHost(),
        ).run(QueryHost(snapshot))
