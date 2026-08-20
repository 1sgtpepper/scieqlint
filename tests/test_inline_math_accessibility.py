from __future__ import annotations

import json
from dataclasses import replace
from pathlib import PurePosixPath

import pytest

from scieqlint.api import check_documents as public_check_documents
from scieqlint.app import _profile_snapshot, check_documents
from scieqlint.config.model import (
    AlgebraConfig,
    ChecksConfig,
    Config,
    ProfileConfig,
    ProfileSeverity,
)
from scieqlint.diag.model import Severity
from scieqlint.engine.portability import PortabilityEngine
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost
from scieqlint.report.json import JsonReporter
from scieqlint.report.sarif import SarifReporter


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("accessible-math.md"),
        text,
        DocumentKind.MARKDOWN,
    )


def accessibility_config(*, severity: ProfileSeverity | None = None) -> Config:
    return Config(
        profile=ProfileConfig(name="math-accessibility", severity=severity),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
    )


def test_accessibility_profile_tracks_only_explicit_inline_math_without_alt() -> None:
    source = r"""Paragraph $x$.

# Heading with {math}`y + 1`

- Item with \(z\)

Inferred text x = y is not an owned inline-math container.

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


def test_public_api_projects_stable_source_owned_accessibility_metadata() -> None:
    result = public_check_documents(
        (doc("A prefix edited before the formula.\nUse $x$ here.\n"),),
        config=accessibility_config(),
        accessibility_metadata={"accessible-math.md::inline-math::dollar::x": "the variable x"},
    )

    assert not any(item.code == "PORT002" for item in result.diagnostics)


def test_accessibility_ids_distinguish_repeated_source_tokens() -> None:
    snapshot = _profile_snapshot((doc("Use $x$, then $x$.\n"),), accessibility_config())

    assert [fact.accessibility_id for fact in snapshot.inline_math[:2]] == [
        "accessible-math.md::inline-math::dollar::x",
        "accessible-math.md::inline-math::dollar::x::1",
    ]


def test_accessibility_ids_do_not_confuse_body_text_with_occurrence_suffixes() -> None:
    document = SourceDocument.from_text(
        PurePosixPath("chapters/math::notes.md"),
        "Use $x$, then $x$, and finally $x::1$.\n",
        DocumentKind.MARKDOWN,
    )
    snapshot = _profile_snapshot((document,), accessibility_config())

    assert [fact.accessibility_id for fact in snapshot.inline_math[:3]] == [
        "chapters%2Fmath%3A%3Anotes.md::inline-math::dollar::x",
        "chapters%2Fmath%3A%3Anotes.md::inline-math::dollar::x::1",
        "chapters%2Fmath%3A%3Anotes.md::inline-math::dollar::x%3A%3A1",
    ]

    result = public_check_documents(
        (document,),
        config=accessibility_config(),
        accessibility_metadata={
            "chapters%2Fmath%3A%3Anotes.md::inline-math::dollar::x": "the variable x",
            "chapters%2Fmath%3A%3Anotes.md::inline-math::dollar::x::1": "the variable x",
            "chapters%2Fmath%3A%3Anotes.md::inline-math::dollar::x%3A%3A1": (
                "the identifier x double-colon one"
            ),
        },
    )

    assert not any(item.code == "PORT002" for item in result.diagnostics)


def test_public_api_rejects_accessibility_metadata_for_unknown_ids() -> None:
    with pytest.raises(ValueError, match="unknown inline math fact"):
        public_check_documents(
            (doc("Use $x$ here.\n"),),
            config=accessibility_config(),
            accessibility_metadata={"unknown-inline": "not a source fact"},
        )


def test_inferred_plain_text_candidates_cannot_accept_accessibility_metadata() -> None:
    with pytest.raises(ValueError, match="unknown inline math fact"):
        public_check_documents(
            (doc("An inferred candidate x = y stays plain text.\n"),),
            config=accessibility_config(),
            accessibility_metadata={
                "accessible-math.md::inline-math::plain-text::x = y": "an equation"
            },
        )


def test_accessibility_engine_emits_fact_backed_metadata_in_source_order() -> None:
    source = "Use $x$ and {math}`y`.\n"
    snapshot = _profile_snapshot((doc(source),), accessibility_config())
    diagnostics = PortabilityEngine(profile="math-accessibility").run(QueryHost(snapshot))

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


@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        ("warning", Severity.WARNING),
        ("error", Severity.ERROR),
        ("disabled", None),
    ],
)
def test_accessibility_profile_uses_configured_policy_severity(
    severity: ProfileSeverity,
    expected: Severity | None,
) -> None:
    result = check_documents(
        (doc("Use $x$.\n"),),
        config=accessibility_config(severity=severity),
    )
    diagnostics = [item for item in result.diagnostics if item.code == "PORT002"]

    if expected is None:
        assert diagnostics == []
    else:
        assert len(diagnostics) == 1
        assert diagnostics[0].severity is expected


def test_unsupported_inline_environment_keeps_accessibility_span_and_status() -> None:
    source = r"Before {math}`\begin{cases}x\end{cases}` after."
    snapshot = _profile_snapshot((doc(source),), accessibility_config())
    [inline] = QueryHost(snapshot).portability.inline_math_missing_alt()
    [diagnostic] = PortabilityEngine(profile="math-accessibility").run(QueryHost(snapshot))

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
    assert json_diagnostic["properties"]["subject_fact_id"] == (
        "accessible-math.md::inline-math::dollar::x"
    )

    sarif_payload = json.loads(SarifReporter().render(result))
    [sarif_result] = [
        item for item in sarif_payload["runs"][0]["results"] if item["ruleId"] == "PORT002"
    ]
    assert sarif_result["properties"]["profile"] == "math-accessibility"
    assert sarif_result["properties"]["accessibility_requirement"] == "accessible-text"


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


def test_portability_engine_rejects_unknown_profile() -> None:
    with pytest.raises(ValueError, match="unsupported portability profile: future"):
        PortabilityEngine(profile="future").run(QueryHost(FactSnapshot()))
