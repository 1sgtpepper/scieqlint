from __future__ import annotations

import json
from pathlib import PurePosixPath

from scieqlint.app import check_documents
from scieqlint.config.load import load_config
from scieqlint.config.model import AlgebraConfig, ChecksConfig, Config, ProfileConfig
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.frontend.myst_refs import _role_title_span
from scieqlint.frontend.myst_shared import ROLE_RE
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost
from scieqlint.report.json import JsonReporter
from scieqlint.source.maps import SourceMap


def doc(text: str, path: str = "paper.md") -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def profile_config(name: str | None = "reference-display") -> Config:
    return Config(
        profile=ProfileConfig(name=name),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
    )


def fixture_source() -> str:
    return r"""(intro)=
# Introduction

(fig-plot)=
```{figure}
plot.png
```

$$
E = mc^2 \label{eq-energy}
$$

Heading [](#intro).
Missing equation [](#eq-energy).
Generic equation [eq-energy](#eq-energy).
Useful equation [Energy balance](#eq-energy).
Missing figure [](#fig-plot).
Useful figure [Theme comparison](#fig-plot).
Typed equation {eq}`eq-energy`.
Generic role {ref}`eq-energy`.
Titled equation {eq}`Energy equation <eq-energy>`.
"""


def test_frontend_tracks_explicit_text_kind_target_type_and_intent() -> None:
    snapshot = MySTFrontend().lower((doc(fixture_source()),))
    facts = snapshot.reference_display_text

    assert [fact.reference_kind for fact in facts] == [
        "markdown-link",
        "markdown-link",
        "markdown-link",
        "markdown-link",
        "markdown-link",
        "markdown-link",
        "eq",
        "ref",
        "eq",
    ]
    assert [fact.target_type for fact in facts] == [
        "heading",
        "equation",
        "equation",
        "equation",
        "figure",
        "figure",
        "equation",
        "equation",
        "equation",
    ]
    assert [fact.display_intent for fact in facts] == [
        "target-default",
        "target-default",
        "explicit",
        "explicit",
        "target-default",
        "explicit",
        "typed-number",
        "target-default",
        "explicit",
    ]
    assert [fact.explicit_text for fact in facts] == [
        None,
        None,
        "eq-energy",
        "Energy balance",
        None,
        "Theme comparison",
        None,
        None,
        "Energy equation",
    ]
    assert all(fact.target_fact_ids for fact in facts)
    generic = facts[2]
    assert generic.display_text_span is not None
    assert fixture_source()[generic.display_text_span.start : generic.display_text_span.end] == (
        "eq-energy"
    )
    titled = facts[-1]
    assert titled.display_text_span is not None
    assert fixture_source()[titled.display_text_span.start : titled.display_text_span.end] == (
        "Energy equation"
    )


def test_query_flags_only_missing_or_generic_nonheading_display_text() -> None:
    snapshot = MySTFrontend().lower((doc(fixture_source()),))

    issues = QueryHost(snapshot).references.unclear_nonheading_display_text()

    assert [(issue.fact.normalized_target, issue.reason) for issue in issues] == [
        ("eq-energy", "missing"),
        ("eq-energy", "generic"),
        ("fig-plot", "missing"),
        ("eq-energy", "missing"),
    ]
    assert all(issue.fact.target_type != "heading" for issue in issues)
    assert all(issue.fact.display_intent != "typed-number" for issue in issues)


def test_query_exposes_display_facts_and_classifies_generic_block_text() -> None:
    snapshot = MySTFrontend().lower(
        (
            doc(
                "(tip)=\n```{note}\nbody\n```\n\nSee [paragraph](#tip).\n",
            ),
        )
    )
    query = QueryHost(snapshot)

    assert query.references.display_text_facts() == snapshot.reference_display_text
    assert [(fact.target_type, fact.explicit_text) for fact in snapshot.reference_display_text] == [
        ("block", "paragraph")
    ]
    assert [
        (issue.fact.normalized_target, issue.reason)
        for issue in query.references.unclear_nonheading_display_text()
    ] == [("tip", "generic")]


def test_unrepresentable_role_title_has_no_source_span() -> None:
    document = doc("{ref}`Readable title <target>`")
    match = ROLE_RE.search(document.text)

    assert match is not None
    assert _role_title_span(SourceMap.for_document(document), match, "not present") is None


def test_reference_display_profile_is_opt_in_and_reports_exact_metadata() -> None:
    source = doc(fixture_source())
    default = check_documents((source,), config=profile_config(None))
    enabled = check_documents((source,), config=profile_config())

    assert not [diagnostic for diagnostic in default.diagnostics if diagnostic.code == "REF009"]
    diagnostics = tuple(
        diagnostic for diagnostic in enabled.diagnostics if diagnostic.code == "REF009"
    )
    assert [(diagnostic.code, diagnostic.profile) for diagnostic in diagnostics] == [
        ("REF009", "reference-display"),
        ("REF009", "reference-display"),
        ("REF009", "reference-display"),
        ("REF009", "reference-display"),
    ]
    assert [dict(diagnostic.properties)["reason"] for diagnostic in diagnostics] == [
        "missing",
        "generic",
        "missing",
        "missing",
    ]
    assert dict(diagnostics[1].properties) == {
        "target": "eq-energy",
        "target_type": "equation",
        "reference_kind": "markdown-link",
        "display_intent": "explicit",
        "display_text": "eq-energy",
        "reason": "generic",
    }
    assert len(diagnostics[1].provenance_ids) == 3
    payload = json.loads(JsonReporter().render(enabled))
    projected = [item for item in payload["diagnostics"] if item["code"] == "REF009"][1]
    assert projected["profile"] == "reference-display"
    assert projected["properties"]["target_type"] == "equation"
    assert projected["provenance_ids"] == list(diagnostics[1].provenance_ids)


def test_typed_equation_roles_and_unresolved_or_ambiguous_targets_stay_quiet() -> None:
    source = doc(
        r"""$$
x = 1 \label{eq-dup}
$$
$$
y = 2 \label{eq-dup}
$$

{eq}`eq-dup` {ref}`missing` [](#eq-dup)
"""
    )
    snapshot = MySTFrontend().lower((source,))

    assert [fact.target_type for fact in snapshot.reference_display_text] == [
        None,
        None,
        None,
    ]
    assert QueryHost(snapshot).references.unclear_nonheading_display_text() == ()
    assert ReferenceEngine(profile="reference-display").run(QueryHost(snapshot))[0].code == (
        "REF001"
    )


def test_display_facts_and_diagnostics_are_document_order_independent() -> None:
    target = doc(
        r"""(fig-plot)=
```{figure}
plot.png
```
""",
        "target.md",
    )
    reference = doc("See [fig-plot](#fig-plot).\n", "reference.md")
    first = MySTFrontend().lower((target, reference))
    second = MySTFrontend().lower((reference, target))

    def contract(snapshot):
        return tuple(
            (
                fact.document_id,
                fact.normalized_target,
                fact.target_type,
                fact.explicit_text,
                fact.target_fact_ids,
            )
            for fact in snapshot.reference_display_text
        )

    assert contract(first) == contract(second)
    assert ReferenceEngine(profile="reference-display").run(QueryHost(first)) == ReferenceEngine(
        profile="reference-display"
    ).run(QueryHost(second))


def test_load_config_accepts_reference_display_profile(tmp_path) -> None:
    path = tmp_path / "scieqlint.toml"
    path.write_text('[profile]\nname = "reference-display"\n', encoding="utf-8")

    loaded = load_config(path)

    assert loaded.profile.name == "reference-display"
