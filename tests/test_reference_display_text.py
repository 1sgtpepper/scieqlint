from __future__ import annotations

import json
from pathlib import PurePosixPath

import pytest

import scieqlint.frontend.reference_display as reference_display
from scieqlint.api import check_documents as public_check_documents
from scieqlint.app import _profile_snapshot, check_documents
from scieqlint.config.load import load_config
from scieqlint.config.model import (
    AlgebraConfig,
    ChecksConfig,
    Config,
    ProfileConfig,
    ProjectConfig,
    ScannerConfig,
)
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.facts.reference import GenericRefFact, TargetAnchorFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.facts.structure import CodeCellFact
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.frontend.reference_display import reference_display_text_facts
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost
from scieqlint.report.json import JsonReporter

_DEFAULT_PROJECT_CONFIG = ProjectConfig()


def doc(text: str, path: str = "paper.md") -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def profile_config(
    name: str | None = "reference-display",
    *,
    project: ProjectConfig = _DEFAULT_PROJECT_CONFIG,
) -> Config:
    return Config(
        profile=ProfileConfig(name=name),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
        project=project,
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
    assert all(fact.target_identity is not None for fact in facts)
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


@pytest.mark.parametrize(
    "label",
    [
        "  **Figure**  ",
        "  <em>Figure</em>  ",
        r"  Figure \[x\]  ",
        "  Figure &amp; x  ",
        "  Café 😀  ",
    ],
)
def test_markdown_display_text_preserves_trimmed_source_label(label: str) -> None:
    source = doc(f"(fig-source)=\n```{{figure}}\nplot.png\n```\n\nSee [{label}](#fig-source).\n")

    [fact] = MySTFrontend().lower((source,)).reference_display_text

    expected = label.strip()
    assert fact.explicit_text == expected
    assert fact.display_text_span is not None
    assert source.text[fact.display_text_span.start : fact.display_text_span.end] == expected


def test_role_display_text_preserves_trimmed_source_label() -> None:
    source = doc(
        "(fig-source)=\n```{figure}\nplot.png\n```\n\nSee {ref}`  **Figure**  <fig-source>`.\n"
    )

    [fact] = MySTFrontend().lower((source,)).reference_display_text

    assert fact.explicit_text == "**Figure**"
    assert fact.display_text_span is not None
    assert source.text[fact.display_text_span.start : fact.display_text_span.end] == "**Figure**"


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


def test_unscoped_query_drives_display_diagnostic_from_stored_fact() -> None:
    source = doc("(fig-plot)=\n```{figure}\nplot.png\n```\n\nSee {ref}`fig-plot`.\n")
    profiled = MySTFrontend().lower((source,))
    snapshot = FactSnapshot(reference_display_text=profiled.reference_display_text)

    [diagnostic] = ReferenceEngine(profile="reference-display").run(QueryHost(snapshot))

    assert diagnostic.code == "REF009"
    assert diagnostic.span is not None
    assert source.text[diagnostic.span.start : diagnostic.span.end] == "{ref}`fig-plot`"
    assert dict(diagnostic.properties) == {
        "target": "paper.md#fig-plot",
        "target_type": "figure",
        "reference_kind": "ref",
        "display_intent": "target-default",
        "display_text": "",
        "reason": "missing",
    }


def test_hidden_reference_source_does_not_produce_display_facts() -> None:
    source = doc("See [](#fig-target).\n", "source.md")
    target = doc("(fig-target)=\n```{figure}\nplot.png\n```\n", "target.md")
    snapshot = _profile_snapshot(
        (source, target),
        profile_config(project=ProjectConfig(visibility=(("source.md", "hidden"),))),
    )

    assert [ref.visibility for ref in snapshot.generic_refs] == ["hidden"]
    assert snapshot.reference_display_text == ()


def test_hidden_equation_reference_source_does_not_produce_display_facts() -> None:
    source = doc("See {eq}`eq-target`.\n", "source.md")
    target = doc("$$\nx = 1\n$$ {#eq-target}\n", "target.md")
    snapshot = _profile_snapshot(
        (source, target),
        profile_config(project=ProjectConfig(visibility=(("source.md", "hidden"),))),
    )

    assert [ref.visibility for ref in snapshot.equation_refs] == ["hidden"]
    assert snapshot.reference_display_text == ()


def test_display_facts_omit_identityless_references() -> None:
    identityless = GenericRefFact(
        fact_id="identityless-ref",
        document_id="paper.md",
        span=None,
        raw=None,
        role_kind="markdown-link",
        target="target",
        normalized_target="target",
    )

    assert reference_display_text_facts((identityless,), (), (), ()) == ()


def test_resolved_heading_kind_wins_over_figure_prefix_in_display_resolution() -> None:
    source = doc("(fig-intro)=\n# Introduction\n\nSee [](#fig-intro).\n")
    snapshot = MySTFrontend().lower((source,))

    [fact] = snapshot.reference_display_text

    assert fact.target_type == "heading"
    assert fact.target_type_source == "resolved"
    assert QueryHost(snapshot).references.unclear_nonheading_display_text() == ()


def test_untyped_targets_fall_back_to_prefix_inference_or_unresolved() -> None:
    prefix_target = TargetAnchorFact(
        fact_id="target-figure",
        document_id="paper.md",
        span=None,
        label="fig-raw",
        normalized_label="fig-raw",
        target_kind=None,
        attaches_to_fact_id=None,
        placement="standalone",
    )
    unknown_target = TargetAnchorFact(
        fact_id="target-unknown",
        document_id="paper.md",
        span=None,
        label="custom-target",
        normalized_label="custom-target",
        target_kind=None,
        attaches_to_fact_id=None,
        placement="standalone",
    )
    refs = tuple(
        GenericRefFact(
            fact_id=f"ref-{target}",
            document_id="paper.md",
            span=None,
            raw=None,
            role_kind="ref",
            target=target,
            normalized_target=target,
        )
        for target in ("fig-raw", "custom-target")
    )

    facts = reference_display_text_facts(
        refs,
        (),
        (prefix_target, unknown_target),
        (),
    )

    assert [
        (fact.normalized_target, fact.target_type, fact.target_type_source) for fact in facts
    ] == [
        ("custom-target", None, "unresolved"),
        ("fig-raw", "figure", "inferred"),
    ]


def test_explicit_code_cell_metadata_wins_over_prefix_in_display_resolution() -> None:
    source = doc(
        "```{code-cell} python\n"
        ":label: fig-table\n"
        ":tbl-cap: A table\n"
        "value = 1\n"
        "```\n\n"
        "See [](#fig-table).\n"
    )
    snapshot = MySTFrontend().lower((source,))

    [fact] = snapshot.reference_display_text

    assert fact.target_type == "table"
    assert fact.target_type_source == "explicit"


def test_code_cell_listing_and_generic_caption_metadata_resolve_display_types() -> None:
    source = doc(
        "```{code-cell} python\n"
        ":label: lst-cell\n"
        ":lst-cap: A listing\n"
        "value = 1\n"
        "```\n\n"
        "```{code-cell} python\n"
        ":label: block-cell\n"
        ":caption: A block\n"
        "value = 2\n"
        "```\n\n"
        "See [](#lst-cell) and [](#block-cell).\n"
    )
    snapshot = MySTFrontend().lower((source,))

    assert [
        (fact.normalized_target, fact.target_type, fact.target_type_source)
        for fact in snapshot.reference_display_text
    ] == [
        ("lst-cell", "listing", "explicit"),
        ("block-cell", "block", "explicit"),
    ]


@pytest.mark.parametrize(
    ("option", "expected_type"),
    [("fig-subcap", "figure"), ("tbl-subcap", "table")],
)
def test_code_cell_subcaption_metadata_resolves_display_types(
    option: str,
    expected_type: str,
) -> None:
    source = doc(
        "```{code-cell} python\n"
        ":label: plain-cell\n"
        f":{option}: Caption\n"
        "value = 1\n"
        "```\n\n"
        "See [](#plain-cell).\n"
    )

    [fact] = MySTFrontend().lower((source,)).reference_display_text

    assert fact.target_type == expected_type
    assert fact.target_type_source == "explicit"


def test_display_resolution_includes_labeled_code_cells() -> None:
    cell = CodeCellFact(
        fact_id="cell-figure",
        document_id="paper.md",
        span=None,
        raw=None,
        fence_fact_id="fence-figure",
        directive_fact_id=None,
        language="python",
        engine="jupyter",
        options=(("label", "fig-cell"),),
        label="fig-cell",
        normalized_label="fig-cell",
    )
    reference = GenericRefFact(
        fact_id="reference-figure",
        document_id="paper.md",
        span=None,
        raw=None,
        role_kind="ref",
        target="fig-cell",
        normalized_target="fig-cell",
    )

    [display] = reference_display_text_facts((reference,), (), (), (), code_cells=(cell,))

    assert display.target_type == "figure"
    assert display.target_type_source == "inferred"
    assert display.target_fact_ids == (cell.fact_id,)


@pytest.mark.parametrize(
    ("label", "normalized_label"),
    [("fig-cell", None), (None, "fig-cell")],
)
def test_code_cell_fact_rejects_partial_label_identity(
    label: str | None,
    normalized_label: str | None,
) -> None:
    with pytest.raises(
        ValueError,
        match="code-cell label and normalized label must both be present or absent",
    ):
        CodeCellFact(
            fact_id="cell-figure",
            document_id="paper.md",
            span=None,
            raw=None,
            fence_fact_id="fence-figure",
            directive_fact_id=None,
            language="python",
            engine="jupyter",
            options=(),
            label=label,
            normalized_label=normalized_label,
        )


def test_public_reference_role_resolves_labeled_code_cell_target() -> None:
    source = doc(
        "```{code-cell} python\n"
        ":label: fig-cell\n"
        "pass\n"
        "```\n\n"
        "See {ref}`fig-cell` and {ref}`missing-cell`.\n"
    )

    result = public_check_documents(
        (source,),
        config=Config(checks=ChecksConfig(algebra=AlgebraConfig(enabled=False))),
    )
    reference_diagnostics = tuple(
        diagnostic for diagnostic in result.diagnostics if diagnostic.code.startswith("REF")
    )

    assert result.files_checked == 1
    assert [diagnostic.code for diagnostic in reference_diagnostics] == ["REF004"]
    assert reference_diagnostics[0].message.endswith("missing-cell")
    assert reference_diagnostics[0].span is not None
    assert source.text[reference_diagnostics[0].span.start : reference_diagnostics[0].span.end] == (
        "missing-cell"
    )


def test_public_notebook_reference_role_resolves_labeled_code_cell_target() -> None:
    notebook = SourceDocument.from_text(
        PurePosixPath("display.ipynb"),
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": "See {ref}`fig-cell` and {ref}`missing-cell`.\n",
                    },
                    {
                        "cell_type": "code",
                        "execution_count": None,
                        "metadata": {"label": "fig-cell"},
                        "outputs": [],
                        "source": "raise RuntimeError('must not execute')\n",
                    },
                ],
                "metadata": {"kernelspec": {"language": "python", "name": "python3"}},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            sort_keys=True,
        ),
        DocumentKind.NOTEBOOK,
    )

    result = public_check_documents((notebook,), config=profile_config())
    reference_diagnostics = tuple(
        diagnostic for diagnostic in result.diagnostics if diagnostic.code.startswith("REF")
    )

    assert result.files_checked == 1
    assert [diagnostic.code for diagnostic in reference_diagnostics] == ["REF009", "REF004"]
    assert dict(reference_diagnostics[0].properties)["target"] == "display.ipynb#fig-cell"
    assert reference_diagnostics[1].message.endswith("missing-cell")
    assert reference_diagnostics[0].span is not None
    assert notebook.text[
        reference_diagnostics[0].span.start : reference_diagnostics[0].span.end
    ] == ("{ref}`fig-cell`")
    assert reference_diagnostics[1].span is not None
    assert notebook.text[
        reference_diagnostics[1].span.start : reference_diagnostics[1].span.end
    ] == ("missing-cell")


def test_reference_namespace_includes_code_cell_labels_and_preserves_identity() -> None:
    source = doc("```{code-cell} python\n:label: FIG-cell\npass\n```\n\nSee {ref}`FIG-cell`.\n")

    snapshot = MySTFrontend().lower((source,))
    query = QueryHost(snapshot)

    assert query.references.target_index()["FIG-cell"] == (snapshot.code_cells[0],)
    assert query.references.target_identity_index()[(PurePosixPath("paper.md"), "FIG-cell")] == (
        snapshot.code_cells[0],
    )
    assert query.references.unresolved_generic_refs() == ()


def test_duplicate_code_cell_labels_remain_ambiguous_without_new_diagnostic() -> None:
    source = doc(
        "```{code-cell} python\n"
        ":label: repeated-cell\n"
        "pass\n"
        "```\n\n"
        "```{code-cell} python\n"
        ":label: repeated-cell\n"
        "pass\n"
        "```\n\n"
        "See {ref}`repeated-cell`.\n"
    )

    diagnostics = ReferenceEngine().run(QueryHost(MySTFrontend().lower((source,))))

    assert [diagnostic.code for diagnostic in diagnostics] == ["REF005"]


def test_hidden_code_cell_is_not_an_ordinary_reference_target() -> None:
    source = doc("See {ref}`cell-target`.\n", "source.md")
    target = doc(
        "```{code-cell} python\n:label: cell-target\n:fig-cap: Chart\npass\n```\n",
        "target.md",
    )

    visible = check_documents((source, target), config=profile_config())
    hidden = check_documents(
        (source, target),
        config=profile_config(project=ProjectConfig(visibility=(("target.md", "hidden"),))),
    )

    assert [
        diagnostic.code for diagnostic in visible.diagnostics if diagnostic.code == "REF009"
    ] == ["REF009"]
    assert [
        diagnostic.code for diagnostic in hidden.diagnostics if diagnostic.code == "REF009"
    ] == []
    assert [
        diagnostic.code for diagnostic in hidden.diagnostics if diagnostic.code == "REF004"
    ] == ["REF004"]


def test_application_derives_display_facts_only_for_the_opt_in_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = doc("(fig-target)=\n# Target\n\nSee [](#fig-target).\n")
    notebook = SourceDocument.from_text(
        PurePosixPath("display.ipynb"),
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": "See [](#fig-cell).\n",
                    },
                    {
                        "cell_type": "code",
                        "execution_count": None,
                        "metadata": {"label": "fig-cell"},
                        "outputs": [],
                        "source": "plot()\n",
                    },
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            sort_keys=True,
        ),
        DocumentKind.NOTEBOOK,
    )

    def unexpected_derivation(*args, **kwargs):
        raise AssertionError("default application profiles must not derive display facts")

    for owner in (
        "scieqlint.app.reference_display_text_facts",
        "scieqlint.frontend.myst.reference_display_text_facts",
        "scieqlint.frontend.notebook.reference_display_text_facts",
    ):
        monkeypatch.setattr(owner, unexpected_derivation)

    config = profile_config(None)
    snapshot = _profile_snapshot((source, notebook), config)
    result = public_check_documents((source, notebook), config=config)

    assert snapshot.reference_display_text == ()
    assert not [diagnostic for diagnostic in result.diagnostics if diagnostic.code == "REF009"]


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
        "target": "paper.md#eq-energy",
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
    assert all(fact.target_fact_ids == () for fact in snapshot.reference_display_text)
    assert QueryHost(snapshot).references.unclear_nonheading_display_text() == ()
    assert ReferenceEngine(profile="reference-display").run(QueryHost(snapshot))[0].code == (
        "REF001"
    )


def test_explicitly_titled_typed_equation_role_is_checked() -> None:
    source = doc("$$\nx = 1 \\label{eq-energy}\n$$\n\n{eq}`Equation <eq-energy>`.\n")
    snapshot = MySTFrontend().lower((source,))

    [fact] = snapshot.reference_display_text
    assert fact.target_type == "equation"
    assert fact.display_intent == "explicit"
    assert fact.explicit_text == "Equation"
    assert [
        issue.reason for issue in QueryHost(snapshot).references.unclear_nonheading_display_text()
    ] == ["generic"]
    [diagnostic] = [
        item
        for item in ReferenceEngine(profile="reference-display").run(QueryHost(snapshot))
        if item.code == "REF009"
    ]
    assert diagnostic.message.endswith(": eq-energy")


def test_raw_tex_reference_forms_have_typed_number_display_intent() -> None:
    source = doc(
        "\\begin{equation}\nx = 1 \\label{eq-raw} \\eqref{eq-raw} \\ref{eq-raw}\n\\end{equation}\n"
    )

    snapshot = _profile_snapshot((source,), profile_config())
    result = check_documents((source,), config=profile_config())

    raw_facts = tuple(
        fact for fact in snapshot.reference_display_text if fact.reference_kind.startswith("tex-")
    )
    assert [(fact.reference_kind, fact.display_intent) for fact in raw_facts] == [
        ("tex-eqref", "typed-number"),
        ("tex-ref", "typed-number"),
    ]
    assert not [item for item in result.diagnostics if item.code == "REF009"]


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
                fact.target_identity,
                fact.target_fact_ids,
            )
            for fact in snapshot.reference_display_text
        )

    assert contract(first) == contract(second)
    assert ReferenceEngine(profile="reference-display").run(QueryHost(first)) == ReferenceEngine(
        profile="reference-display"
    ).run(QueryHost(second))


def test_display_uses_only_the_visible_cross_document_target() -> None:
    source = doc("See [](target.md#eq-target).\n", "source.md")
    target = doc("$$\nx = 1\n$$ {#eq-target}\n", "target.md")

    visible = check_documents((source, target), config=profile_config())
    hidden = check_documents(
        (source, target),
        config=profile_config(
            project=ProjectConfig(visibility=(("target.md", "hidden"),)),
        ),
    )

    assert [diagnostic.code for diagnostic in visible.diagnostics] == ["REF009"]
    assert [diagnostic.code for diagnostic in hidden.diagnostics] == ["REF004"]
    visible_display = tuple(visible.diagnostics)
    assert len(visible_display) == 1
    assert dict(visible_display[0].properties) == {
        "target": "target.md#eq-target",
        "target_type": "equation",
        "reference_kind": "markdown-link",
        "display_intent": "target-default",
        "display_text": "",
        "reason": "missing",
    }


def test_display_uses_the_complete_path_and_fragment_identity() -> None:
    source = doc("See [](target.md#shared).\n", "source.md")
    target = doc("(shared)=\n# Target heading\n", "target.md")
    other = doc("$$\nx = 1\n$$ {#shared}\n", "other.md")

    snapshot = MySTFrontend().lower((source, target, other))

    [display] = snapshot.reference_display_text
    assert display.target_type == "heading"
    assert display.target_identity == (PurePosixPath("target.md"), "shared")
    assert display.target_fact_ids == ("target.md::anchor::0",)


def test_pathless_role_selects_a_cross_document_target_identity() -> None:
    source = doc("See {ref}`shared`.\n", "source.md")
    target = doc("(shared)=\n```{figure}\nplot.png\n```\n", "target.md")

    snapshot = MySTFrontend().lower((source, target))

    [display] = snapshot.reference_display_text
    assert display.target_type == "figure"
    assert display.target_identity == (PurePosixPath("target.md"), "shared")
    result = check_documents((source, target), config=profile_config())
    [diagnostic] = [item for item in result.diagnostics if item.code == "REF009"]
    assert dict(diagnostic.properties)["target"] == "target.md#shared"


def test_pathless_role_with_duplicate_member_targets_is_ambiguous() -> None:
    source = doc("See {ref}`shared`.\n", "source.md")
    first = doc("(shared)=\n```{figure}\nfirst.png\n```\n", "first.md")
    second = doc("(shared)=\n```{figure}\nsecond.png\n```\n", "second.md")

    snapshot = MySTFrontend().lower((source, first, second))
    result = check_documents((source, first, second), config=profile_config())

    [display] = snapshot.reference_display_text
    assert display.target_type_source == "ambiguous"
    assert display.target_identity is None
    assert display.target_fact_ids == ()
    assert [item.code for item in result.diagnostics if item.code == "REF005"] == ["REF005"]
    assert not [item for item in result.diagnostics if item.code == "REF009"]


def test_display_resolution_indexes_label_and_member_identities_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_count = 32
    normalize_calls = 0
    normalize = reference_display.normalize_project_path

    def counting_normalize(*args, **kwargs):
        nonlocal normalize_calls
        normalize_calls += 1
        return normalize(*args, **kwargs)

    monkeypatch.setattr(reference_display, "normalize_project_path", counting_normalize)
    source = doc(
        "".join("See {ref}`shared`.\n" for _ in range(target_count))
        + "".join(f"See [](target-{index:02d}.md#shared).\n" for index in range(target_count)),
        "source.md",
    )
    targets = tuple(
        doc(f"(shared)=\n# Target {index}\n", f"target-{index:02d}.md")
        for index in range(target_count)
    )

    snapshot = MySTFrontend().lower((source, *reversed(targets)))

    ambiguous = snapshot.reference_display_text[:target_count]
    selected = snapshot.reference_display_text[target_count:]
    assert len(snapshot.reference_display_text) == target_count * 2
    assert normalize_calls <= target_count * 2
    assert all(
        fact.target_type_source == "ambiguous"
        and fact.target_identity is None
        and fact.target_fact_ids == ()
        for fact in ambiguous
    )
    assert [(fact.target_identity, fact.target_fact_ids) for fact in selected] == [
        (
            (PurePosixPath(f"target-{index:02d}.md"), "shared"),
            (f"target-{index:02d}.md::anchor::0",),
        )
        for index in range(target_count)
    ]
    assert QueryHost(snapshot).references.unclear_nonheading_display_text() == ()


def test_display_resolution_applies_visibility_before_matching_targets() -> None:
    source = doc("See [](target.md#shared).\n", "source.md")
    hidden_target = doc("(shared)=\n# Hidden heading\n", "target.md")
    visible_same_label = doc("$$\nx = 1\n$$ {#shared}\n", "other.md")
    config = profile_config(
        project=ProjectConfig(visibility=(("target.md", "hidden"),)),
    )

    snapshot = _profile_snapshot((source, hidden_target, visible_same_label), config)

    [display] = snapshot.reference_display_text
    assert display.target_type is None
    assert display.target_fact_ids == ()


def test_public_reference_display_profile_admits_notebook_targets() -> None:
    notebook = SourceDocument.from_text(
        PurePosixPath("display.ipynb"),
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": "See [](#fig-output).\n",
                    },
                    {
                        "cell_type": "code",
                        "execution_count": None,
                        "metadata": {},
                        "outputs": [
                            {
                                "data": {"image/png": "payload"},
                                "metadata": {
                                    "label": "fig-output",
                                    "fig-cap": "Plot",
                                },
                                "output_type": "display_data",
                            }
                        ],
                        "source": "raise RuntimeError('must not execute')\n",
                    },
                ],
                "metadata": {"kernelspec": {"language": "python", "name": "python3"}},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            sort_keys=True,
        ),
        DocumentKind.NOTEBOOK,
    )

    default = public_check_documents((notebook,), config=profile_config(None))
    enabled = public_check_documents((notebook,), config=profile_config())

    assert not [item for item in default.diagnostics if item.code == "REF009"]
    [diagnostic] = [item for item in enabled.diagnostics if item.code == "REF009"]
    assert diagnostic.profile == "reference-display"
    assert dict(diagnostic.properties) == {
        "target": "display.ipynb#fig-output",
        "target_type": "figure",
        "reference_kind": "markdown-link",
        "display_intent": "target-default",
        "display_text": "",
        "reason": "missing",
    }


def test_public_reference_display_profile_admits_markdown_when_scanner_is_disabled() -> None:
    source = doc("(fig-target)=\n```{figure}\nplot.png\n```\n\nSee [](#fig-target).\n")
    profile = Config(
        profile=ProfileConfig(name="reference-display"),
        scanner=ScannerConfig(markdown=False),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
    )

    result = public_check_documents((source,), config=profile)

    [diagnostic] = [item for item in result.diagnostics if item.code == "REF009"]
    assert diagnostic.profile == "reference-display"
    assert dict(diagnostic.properties)["target"] == "paper.md#fig-target"
    assert dict(diagnostic.properties)["target_type"] == "figure"


def test_public_reference_display_profile_admits_notebook_markdown_when_scanner_is_disabled() -> (
    None
):
    notebook = SourceDocument.from_text(
        PurePosixPath("display.ipynb"),
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": "See [](#fig-output).\n",
                    },
                    {
                        "cell_type": "code",
                        "execution_count": None,
                        "metadata": {},
                        "outputs": [
                            {
                                "data": {"image/png": "payload"},
                                "metadata": {"label": "fig-output"},
                                "output_type": "display_data",
                            }
                        ],
                        "source": "raise RuntimeError('must not execute')\n",
                    },
                ],
                "metadata": {"kernelspec": {"language": "python", "name": "python3"}},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            sort_keys=True,
        ),
        DocumentKind.NOTEBOOK,
    )
    profile = Config(
        profile=ProfileConfig(name="reference-display"),
        scanner=ScannerConfig(markdown=False),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
    )

    result = public_check_documents((notebook,), config=profile)

    [diagnostic] = [item for item in result.diagnostics if item.code == "REF009"]
    assert diagnostic.profile == "reference-display"
    assert dict(diagnostic.properties)["target"] == "display.ipynb#fig-output"


def test_notebook_explicit_display_text_retains_its_json_span() -> None:
    notebook = SourceDocument.from_text(
        PurePosixPath("display.ipynb"),
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": "See [figure](#fig-output).\n",
                    },
                    {
                        "cell_type": "code",
                        "execution_count": None,
                        "metadata": {"label": "fig-output"},
                        "outputs": [],
                        "source": "plot()\n",
                    },
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            sort_keys=True,
        ),
        DocumentKind.NOTEBOOK,
    )

    snapshot = _profile_snapshot((notebook,), profile_config())
    result = check_documents((notebook,), config=profile_config())

    [display] = snapshot.reference_display_text
    assert display.display_text_span is not None
    assert display.display_text_span.cell == 0
    assert (
        notebook.text[display.display_text_span.start : display.display_text_span.end] == "figure"
    )
    [diagnostic] = [item for item in result.diagnostics if item.code == "REF009"]
    assert diagnostic.span == display.display_text_span
    assert dict(diagnostic.properties)["reason"] == "generic"


def test_load_config_accepts_reference_display_profile(tmp_path) -> None:
    path = tmp_path / "scieqlint.toml"
    path.write_text('[profile]\nname = "reference-display"\n', encoding="utf-8")

    loaded = load_config(path)

    assert loaded.profile.name == "reference-display"
