from __future__ import annotations

import json
from pathlib import PurePosixPath

import pytest

from scieqlint.app import _profile_snapshot, check_documents
from scieqlint.config.model import AlgebraConfig, ChecksConfig, Config, ProfileConfig
from scieqlint.engine.portability import PortabilityEngine
from scieqlint.facts.portability import OutputPortabilityFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.query.host import QueryHost
from scieqlint.report.json import JsonReporter
from scieqlint.report.sarif import SarifReporter


def doc(text: str) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("typst-equations.md"),
        text,
        DocumentKind.MARKDOWN,
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


def test_typst_engine_emits_fact_backed_metadata_in_source_order() -> None:
    snapshot = _profile_snapshot((doc(_SOURCE),), typst_config())
    diagnostics = PortabilityEngine(profile="typst-portability").run(QueryHost(snapshot))

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


def test_typst_portability_is_deterministic_after_newline_normalization() -> None:
    lf = _profile_snapshot((doc(_SOURCE),), typst_config())
    crlf = _profile_snapshot(
        (doc(_SOURCE.replace("\n", "\r\n")),),
        typst_config(),
    )

    assert lf.display_math == crlf.display_math
    assert lf.portability == crlf.portability
    assert PortabilityEngine(profile="typst-portability").run(QueryHost(lf)) == PortabilityEngine(
        profile="typst-portability"
    ).run(QueryHost(crlf))


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
        PortabilityEngine(profile="typst-portability").run(
            QueryHost(FactSnapshot(portability=(foreign,)))
        )


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
        PortabilityEngine(profile="typst-portability").run(
            QueryHost(FactSnapshot(portability=(unknown,)))
        )
