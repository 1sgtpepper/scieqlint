from __future__ import annotations

import json
from dataclasses import replace
from importlib import resources
from pathlib import Path, PurePosixPath

import pytest
from jsonschema.validators import Draft202012Validator
from referencing import Registry, Resource

from scieqlint.api import check_documents
from scieqlint.app import _profile_snapshot
from scieqlint.config.model import AlgebraConfig, ChecksConfig, Config, ProfileConfig
from scieqlint.engine.portability import PortabilityEngine
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.parse.math import MathHost
from scieqlint.policy import PolicyHost
from scieqlint.query.host import QueryHost
from scieqlint.report.github import GitHubReporter
from scieqlint.report.json import JsonReporter
from scieqlint.report.sarif import SarifReporter
from scieqlint.report.text import TextReporter


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("typst-equations.md"),
        text,
        DocumentKind.MARKDOWN,
    )


def latex_doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("typst-equations.tex"),
        text,
        DocumentKind.LATEX,
    )


def notebook_doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("typst-equations.ipynb"),
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


def typst_config() -> Config:
    return Config(
        profile=ProfileConfig(name="typst-portability"),
        checks=ChecksConfig(algebra=AlgebraConfig(enabled=False)),
    )


_SOURCE = r"""$$
\left\{\begin{matrix}
\begin{aligned}
Y &= \dfrac{x}{2} + \argmin_x f(x)
\end{aligned}
\end{matrix}\right.
$$
"""


def test_typst_profile_materializes_exact_source_spanned_math_risks() -> None:
    snapshot = _profile_snapshot((doc(_SOURCE),), typst_config())

    assert [fact.risk_kind for fact in snapshot.portability] == [
        "typst-fragile-environment",
        "typst-fragile-environment",
        "typst-unsupported-command",
        "typst-unsupported-command",
    ]
    assert [fact.raw for fact in snapshot.portability] == [
        r"\begin{matrix}",
        r"\begin{aligned}",
        r"\dfrac",
        r"\argmin",
    ]
    assert [
        _SOURCE[fact.span.start : fact.span.end]
        for fact in snapshot.portability
        if fact.span is not None
    ] == [
        r"\begin{matrix}",
        r"\begin{aligned}",
        r"\dfrac",
        r"\argmin",
    ]
    assert [dict(fact.metadata) for fact in snapshot.portability] == [
        {
            "syntax_kind": "environment",
            "environment": "matrix",
            "delimiter_commands": "left,right",
        },
        {
            "syntax_kind": "environment",
            "environment": "aligned",
            "delimiter_commands": "left,right",
        },
        {"syntax_kind": "command", "token": r"\dfrac", "command": "dfrac"},
        {"syntax_kind": "command", "token": r"\argmin", "command": "argmin"},
    ]
    assert all(fact.output_profile == "typst" for fact in snapshot.portability)
    assert all(
        fact.subject_fact_id == snapshot.display_math[0].fact_id for fact in snapshot.portability
    )


@pytest.mark.parametrize(
    "source",
    [
        r"\[\dfrac{x}{2}\]",
        r"$$\dfrac{x}{2}$$",
        r"\begin{equation}\dfrac{x}{2}\end{equation}",
    ],
    ids=("bracketed", "dollar", "equation"),
)
def test_typst_profile_uses_latex_scanner_for_tex_display_forms(source: str) -> None:
    snapshot = _profile_snapshot((latex_doc(source),), typst_config())

    assert [(fact.container, fact.body) for fact in snapshot.display_math] == [
        ("latex-display", r"\dfrac{x}{2}")
    ]
    assert [fact.raw for fact in snapshot.portability] == [r"\dfrac"]
    [risk] = snapshot.portability
    assert risk.span is not None
    assert source[risk.span.start : risk.span.end] == r"\dfrac"


@pytest.mark.public_regression
def test_typst_profile_rejects_duplicate_paths_across_document_kinds() -> None:
    path = PurePosixPath("same.md")
    markdown = SourceDocument.from_text(path, "ordinary text\n", DocumentKind.MARKDOWN)
    latex = SourceDocument.from_text(path, r"\[\dfrac{x}{2}\]", DocumentKind.LATEX)

    with pytest.raises(ValueError, match=r"^duplicate document path\(s\): same\.md$"):
        check_documents((markdown, latex), config=typst_config())


def test_typst_profile_rejects_duplicate_same_kind_document_paths() -> None:
    risky = doc(r"$$\dfrac{x}{2}$$")
    safe = doc(r"$$\frac{x}{2}$$")

    with pytest.raises(
        ValueError,
        match=r"^duplicate document path\(s\): typst-equations\.md$",
    ):
        check_documents((risky, safe), config=typst_config())


@pytest.mark.public_regression
def test_typst_suppression_covers_complete_raw_markdown_display() -> None:
    source = """<!-- scieqlint-disable-next-line PORT003 -->
Ordinary prose.
<!-- scieqlint-disable-next-line PORT003 -->
\\begin{equation}
\\left.\\begin{matrix}
x
\\end{matrix}\\right.
\\end{equation}

\\begin{equation}
\\left.\\begin{matrix}
y
\\end{matrix}\\right.
\\end{equation}
"""
    try:
        result = check_documents((doc(source),), config=typst_config())
    except ValueError as exc:
        pytest.fail(f"Typst raw-display suppression was unavailable: {exc}")

    assert [
        (
            diagnostic.code,
            (
                source[diagnostic.span.start : diagnostic.span.end]
                if diagnostic.span is not None
                else None
            ),
            diagnostic.span.line if diagnostic.span is not None else None,
            diagnostic.span.end_line if diagnostic.span is not None else None,
            diagnostic.suppressed,
            diagnostic.suppression_reason,
        )
        for diagnostic in result.diagnostics
        if diagnostic.code == "PORT003"
    ] == [
        ("PORT003", r"\begin{matrix}", 5, 5, True, "source comment"),
        ("PORT003", r"\begin{matrix}", 11, 11, False, None),
    ]
    assert result.math_blocks_checked == 0


def test_typst_profile_uses_latex_scanner_for_tex_nested_environment_risks() -> None:
    source = r"""\begin{equation}
\left.\begin{aligned}
x &= y
\end{aligned}\right.
\end{equation}
"""

    snapshot = _profile_snapshot((latex_doc(source),), typst_config())

    assert [(fact.container, fact.environment) for fact in snapshot.display_math] == [
        ("latex-display", "equation")
    ]
    assert [dict(fact.metadata)["environment"] for fact in snapshot.portability] == ["aligned"]


def test_typst_profile_preserves_latex_comment_and_unterminated_boundaries() -> None:
    commented = r"""\[
% \dfrac{x}{2}
x = 1
\]
"""
    unterminated = r"\[\dfrac{x}{2}"

    commented_snapshot = _profile_snapshot((latex_doc(commented),), typst_config())
    unterminated_snapshot = _profile_snapshot((latex_doc(unterminated),), typst_config())

    assert commented_snapshot.portability == ()
    assert unterminated_snapshot.display_math == ()
    assert unterminated_snapshot.portability == ()


def test_typst_engine_emits_fact_backed_metadata_in_source_order() -> None:
    snapshot = _profile_snapshot((doc(_SOURCE),), typst_config())
    diagnostics = PortabilityEngine(
        profile="typst-portability",
        policy=PolicyHost(),
    ).run(QueryHost(snapshot))

    assert [(item.code, item.profile) for item in diagnostics] == [
        ("PORT003", "typst-portability"),
        ("PORT003", "typst-portability"),
        ("PORT003", "typst-portability"),
        ("PORT003", "typst-portability"),
    ]
    assert [dict(item.properties)["syntax_kind"] for item in diagnostics] == [
        "environment",
        "environment",
        "command",
        "command",
    ]
    assert dict(diagnostics[0].properties)["environment"] == "matrix"
    assert dict(diagnostics[2].properties)["token"] == r"\dfrac"
    assert all(dict(item.properties)["output_profile"] == "typst" for item in diagnostics)


def test_typst_profile_ignores_supported_out_of_scope_and_code_owned_forms() -> None:
    source = r"""$$
\begin{aligned}
x &= \frac{a}{b} + \operatorname{argmin}_t f(t)
\end{aligned}
$$

Inline $\dfrac{x}{y}$ is outside the display-only contract.

```tex
$$
\left\{\begin{matrix}\dfrac{x}{y}\end{matrix}\right.
$$
```

$$
\\dfrac + \argminimum
$$
"""
    snapshot = _profile_snapshot((doc(source),), typst_config())

    assert snapshot.display_math
    assert snapshot.portability == ()
    assert not any(
        item.code == "PORT003"
        for item in check_documents(
            (doc(source),),
            config=typst_config(),
        ).diagnostics
    )


def test_typst_portability_preserves_escape_parity_for_commands_and_environments() -> None:
    even = "\\" * 2
    odd = "\\"
    source = (
        "$$\n"
        + even
        + "dfrac + "
        + odd
        + "dfrac\n"
        + even
        + "begin{matrix}\n"
        + odd
        + "left. "
        + odd
        + "begin{matrix}\n"
        + "$$\n"
    )

    snapshot = _profile_snapshot((doc(source),), typst_config())

    assert [fact.raw for fact in snapshot.portability] == [
        r"\dfrac",
        r"\begin{matrix}",
    ]


def test_typst_fragile_environment_requires_sizing_delimiter_context() -> None:
    without_delimiter = r"""$$
\begin{matrix}
x & y
\end{matrix}
$$
"""
    with_left_only = r"""$$
\left.\begin{array}{ll}
x & y
\end{array}
$$
"""

    quiet = _profile_snapshot((doc(without_delimiter),), typst_config())
    risky = _profile_snapshot((doc(with_left_only),), typst_config())

    assert quiet.portability == ()
    [risk] = risky.portability
    assert dict(risk.metadata) == {
        "syntax_kind": "environment",
        "environment": "array",
        "delimiter_commands": "left",
    }


def test_typst_fragile_environment_does_not_leak_context_between_siblings() -> None:
    source = r"""$$
\begin{matrix}
x & y
\end{matrix}
\left.\begin{aligned}
a &= b
\end{aligned}\right.
$$
"""

    snapshot = _profile_snapshot((doc(source),), typst_config())

    assert [fact.raw for fact in snapshot.portability] == [r"\begin{aligned}"]
    [risk] = snapshot.portability
    assert risk.span is not None
    assert source[risk.span.start : risk.span.end] == r"\begin{aligned}"
    assert dict(risk.metadata)["delimiter_commands"] == "left,right"


def test_typst_nested_delimiter_context_does_not_reach_an_opposite_sibling() -> None:
    source = r"""$$
\begin{array}{c}
\begin{matrix}
\left. x \right.
\end{matrix}
\begin{aligned}
y &= z
\end{aligned}
\end{array}
$$
"""

    snapshot = _profile_snapshot((doc(source),), typst_config())

    assert [fact.raw for fact in snapshot.portability] == [
        r"\begin{array}",
        r"\begin{matrix}",
    ]
    assert [dict(fact.metadata)["environment"] for fact in snapshot.portability] == [
        "array",
        "matrix",
    ]


def test_typst_environment_metadata_preserves_relevant_delimiter_order() -> None:
    source = r"""$$
\begin{matrix}
\right. x \left.
\end{matrix}
$$
"""

    snapshot = _profile_snapshot((doc(source),), typst_config())

    [risk] = snapshot.portability
    assert dict(risk.metadata)["delimiter_commands"] == "right,left"


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            r"""$$
\begin{matrix}
\begin{equation}
\left. x \right.
\end{matrix}
\end{equation}
$$
""",
            id="fragile-closer-while-nonfragile-open",
        ),
        pytest.param(
            r"""$$
\begin{equation}
\begin{matrix}
\left. x \right.
\end{equation}
\end{matrix}
$$
""",
            id="nonfragile-closer-while-fragile-open",
        ),
        pytest.param(
            r"""$$
\end{matrix}
\left.\begin{matrix}x\end{matrix}\right.
$$
""",
            id="unmatched-closer-before-valid-fragile-environment",
        ),
    ],
)
def test_typst_profile_bounds_mismatched_environment_closers(source: str) -> None:
    document = doc(source)
    snapshot = _profile_snapshot((document,), typst_config())

    assert [(fact.raw, dict(fact.metadata)) for fact in snapshot.portability] == [
        (
            r"\begin{matrix}",
            {
                "syntax_kind": "environment",
                "environment": "matrix",
                "delimiter_commands": "left,right",
            },
        )
    ]
    [risk] = snapshot.portability
    assert risk.span is not None
    assert source[risk.span.start : risk.span.end] == r"\begin{matrix}"

    result = check_documents((document,), config=typst_config())
    [diagnostic] = [item for item in result.diagnostics if item.code == "PORT003"]
    properties = dict(diagnostic.properties)
    assert diagnostic.profile == "typst-portability"
    assert properties["environment"] == "matrix"
    assert properties["delimiter_commands"] == "left,right"


def test_typst_profile_extends_unclosed_fragile_environment_to_display_end() -> None:
    source = r"""$$
\begin{equation}
\begin{matrix}
\left. x \right.
$$
"""
    document = doc(source)
    snapshot = _profile_snapshot((document,), typst_config())

    assert [(fact.raw, dict(fact.metadata)) for fact in snapshot.portability] == [
        (
            r"\begin{matrix}",
            {
                "syntax_kind": "environment",
                "environment": "matrix",
                "delimiter_commands": "left,right",
            },
        )
    ]
    [risk] = snapshot.portability
    assert risk.span is not None
    assert source[risk.span.start : risk.span.end] == r"\begin{matrix}"

    result = check_documents((document,), config=typst_config())
    [diagnostic] = [item for item in result.diagnostics if item.code == "PORT003"]
    properties = dict(diagnostic.properties)
    assert diagnostic.profile == "typst-portability"
    assert properties["environment"] == "matrix"
    assert properties["delimiter_commands"] == "left,right"


def test_typst_fragile_environment_preserves_unmatched_right_context() -> None:
    source = r"""$$
\begin{matrix}
x
\end{matrix}\right.
$$
"""

    snapshot = _profile_snapshot((doc(source),), typst_config())

    [risk] = snapshot.portability
    assert dict(risk.metadata)["delimiter_commands"] == "right"


def test_typst_portability_ignores_verbatim_environment_contents() -> None:
    source = r"""$$
\begin{array}
\begin{verbatim}
\left.\begin{matrix}x\end{matrix}\right.
\end{verbatim}
\end{array}
$$
"""

    snapshot = _profile_snapshot((doc(source),), typst_config())

    assert snapshot.portability == ()


def test_typst_portability_masks_nested_non_math_environment_contents() -> None:
    source = r"""$$
\begin{array}
\begin{figure}
\left.\begin{matrix}x\end{matrix}\right.
\dfrac{x}{2}
\end{figure}
\left.\begin{matrix}y\end{matrix}\right.
\end{array}
$$
"""

    snapshot = _profile_snapshot((doc(source),), typst_config())

    assert [fact.raw for fact in snapshot.portability] == [
        r"\begin{array}",
        r"\begin{matrix}",
    ]
    assert all(
        source[fact.span.start : fact.span.end] == fact.raw
        for fact in snapshot.portability
        if fact.span is not None
    )


@pytest.mark.parametrize("closer_prefix", ["% ", "\\\\"])
def test_typst_portability_resumes_after_exact_verbatim_closer(closer_prefix: str) -> None:
    source = (
        "$$\n"
        f"\\begin{{verbatim}}{closer_prefix}\\end{{verbatim}}\n"
        "\\left.\\begin{matrix}x\\end{matrix}\\right.\n"
        "$$\n"
    )

    snapshot = _profile_snapshot((doc(source),), typst_config())

    [risk] = snapshot.portability
    assert risk.raw == r"\begin{matrix}"


def test_unclosed_raw_environment_preserves_typst_risk_to_eof() -> None:
    source = r"""Before.

\begin{matrix}
\left. x &= y
"""
    snapshot = _profile_snapshot((doc(source),), typst_config())

    [display] = snapshot.display_math
    assert display.span is not None
    assert display.span.end == len(source)
    [unknown] = snapshot.unknown_math
    assert (unknown.reason, unknown.excerpt) == ("environment", "matrix")
    [risk] = snapshot.portability
    assert risk.span is not None
    assert source[risk.span.start : risk.span.end] == r"\begin{matrix}"
    assert dict(risk.metadata)["environment"] == "matrix"


def test_nested_environment_remains_owned_by_outer_display_fact() -> None:
    source = r"""\begin{equation}
\left\{\begin{aligned}
x &= y
\end{aligned}\right.
\end{equation}
"""
    snapshot = _profile_snapshot((doc(source),), typst_config())

    assert len(snapshot.display_math) == 1
    [risk] = snapshot.portability
    assert risk.subject_fact_id == snapshot.display_math[0].fact_id
    assert dict(risk.metadata)["environment"] == "aligned"


def test_typst_portability_is_opt_in_and_does_not_run_a_renderer() -> None:
    document = doc(_SOURCE)
    default = check_documents(
        (document,),
        config=Config(checks=ChecksConfig(algebra=AlgebraConfig(enabled=False))),
    )
    profiled = check_documents((document,), config=typst_config())

    assert not any(item.code == "PORT003" for item in default.diagnostics)
    assert [item.code for item in profiled.diagnostics if item.code == "PORT003"] == [
        "PORT003",
        "PORT003",
        "PORT003",
        "PORT003",
    ]


def test_typst_portability_excludes_notebook_markdown_cells_by_contract() -> None:
    result = check_documents((notebook_doc(_SOURCE),), config=typst_config())

    assert result.files_checked == 1
    assert not any(item.code == "PORT003" for item in result.diagnostics)


def test_typst_json_and_sarif_project_profile_and_source_metadata() -> None:
    result = check_documents((doc(_SOURCE),), config=typst_config())

    json_payload = json.loads(JsonReporter().render(result))
    json_diagnostics = [item for item in json_payload["diagnostics"] if item["code"] == "PORT003"]
    assert json_diagnostics[0]["profile"] == "typst-portability"
    assert json_diagnostics[0]["properties"]["output_profile"] == "typst"
    assert json_diagnostics[0]["properties"]["environment"] == "matrix"
    assert json_diagnostics[2]["properties"]["token"] == r"\dfrac"

    sarif_payload = json.loads(SarifReporter().render(result))
    sarif_diagnostics = [
        item for item in sarif_payload["runs"][0]["results"] if item["ruleId"] == "PORT003"
    ]
    assert sarif_diagnostics[0]["properties"]["profile"] == "typst-portability"
    assert sarif_diagnostics[0]["properties"]["output_profile"] == "typst"
    assert sarif_diagnostics[0]["properties"]["environment"] == "matrix"
    assert sarif_diagnostics[2]["properties"]["token"] == r"\dfrac"


def _typst_fixture_result():
    path = Path("tests/fixtures/bad/typst_portability_bad.md")
    document = SourceDocument.from_text(
        PurePosixPath(path.as_posix()),
        path.read_text(encoding="utf-8"),
        DocumentKind.MARKDOWN,
    )
    return check_documents((document,), config=typst_config())


def test_typst_portability_text_golden_output() -> None:
    expected = Path("tests/golden/text/typst_portability_bad.txt").read_text(encoding="utf-8")

    assert TextReporter().render(_typst_fixture_result()) == expected


def test_typst_portability_github_golden_output() -> None:
    expected = Path("tests/golden/github/typst_portability_bad.txt").read_text(encoding="utf-8")

    assert GitHubReporter().render(_typst_fixture_result()) == expected


def test_typst_portability_json_golden_output() -> None:
    expected = Path("tests/golden/json/typst_portability_bad.json").read_text(encoding="utf-8")

    _validate_typst_json_result(expected)
    assert JsonReporter().render(_typst_fixture_result()) == expected


def test_typst_portability_sarif_golden_output() -> None:
    expected = Path("tests/golden/sarif/typst_portability_bad.sarif").read_text(encoding="utf-8")

    assert SarifReporter().render(_typst_fixture_result()) == expected


def _validate_typst_json_result(rendered: str) -> None:
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
    Draft202012Validator(result_schema, registry=registry).validate(json.loads(rendered))


def test_typst_portability_is_deterministic_after_newline_normalization() -> None:
    lf = _profile_snapshot((doc(_SOURCE),), typst_config())
    crlf = _profile_snapshot(
        (doc(_SOURCE.replace("\n", "\r\n")),),
        typst_config(),
    )

    assert lf.display_math == crlf.display_math
    assert lf.portability == crlf.portability
    policy = PolicyHost()
    assert PortabilityEngine(profile="typst-portability", policy=policy).run(
        QueryHost(lf)
    ) == PortabilityEngine(profile="typst-portability", policy=policy).run(QueryHost(crlf))


def test_frontend_without_profile_keeps_typst_policy_unmaterialized() -> None:
    snapshot = MySTFrontend().lower((doc(_SOURCE),))

    assert snapshot.display_math
    assert snapshot.portability == ()


def test_typst_engine_rejects_foreign_risk_kind() -> None:
    foreign = OutputPortabilityFact(
        fact_id="foreign-risk",
        document_id="typst-equations.md",
        span=None,
        subject_fact_id="subject",
        output_profile="typst",
        risk_kind="future-typst-risk",
    )

    with pytest.raises(
        ValueError,
        match="unsupported Typst portability risk kind: future-typst-risk",
    ):
        PortabilityEngine(
            profile="typst-portability",
            policy=PolicyHost(),
        ).run(QueryHost(FactSnapshot(portability=(foreign,))))


def test_typst_engine_rejects_unknown_syntax_kind() -> None:
    unknown = OutputPortabilityFact(
        fact_id="unknown-syntax",
        document_id="typst-equations.md",
        span=None,
        subject_fact_id="subject",
        output_profile="typst",
        risk_kind="typst-unsupported-command",
        metadata=(("syntax_kind", "future"),),
    )

    with pytest.raises(ValueError, match="unsupported Typst syntax kind: future"):
        PortabilityEngine(
            profile="typst-portability",
            policy=PolicyHost(),
        ).run(QueryHost(FactSnapshot(portability=(unknown,))))


def test_typst_risk_projection_skips_unspanned_or_foreign_displays() -> None:
    snapshot = MySTFrontend().lower((doc(r"$$\dfrac{x}{2}$$"),))
    [display] = snapshot.display_math
    invalid = replace(
        snapshot,
        display_math=(
            replace(display, span=None),
            replace(display, document_id="other.md"),
        ),
    )

    assert MathHost().typst_portability(invalid) == ()
