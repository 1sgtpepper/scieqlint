from scieqlint.engine.math_container import MathContainerEngine
from scieqlint.facts.math import DisplayMathFact, InlineMathFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.math.host import MathHost
from scieqlint.query.host import QueryHost


def display_math(body: str, *, label_fact_ids: tuple[str, ...] = ()) -> DisplayMathFact:
    return DisplayMathFact(
        fact_id=f"display::{body}",
        document_id="lecture.md",
        span=None,
        raw=body,
        body=body,
        container="ams",
        label_fact_ids=label_fact_ids,
    )


def inline_math(body: str) -> InlineMathFact:
    return InlineMathFact(
        fact_id=f"inline::{body}",
        document_id="lecture.md",
        span=None,
        raw=f"${body}$",
        body=body,
        delimiter_kind="dollar",
        context="paragraph",
    )


def test_math_host_classifies_unknown_math_reasons():
    snapshot = FactSnapshot(
        display_math=(display_math(r"\begin{align}x&=y\end{align}"),),
        inline_math=(
            inline_math(r"\newcommand{\R}{\mathbb{R}}"),
            inline_math(r"x \overset{?}{=} y"),
        ),
    )

    classified = MathHost().classify(snapshot)

    assert [fact.reason for fact in classified.unknown_math] == [
        "environment",
        "macro",
        "unsupported_operator",
    ]


def test_math_host_classifies_suspicious_generated_formula_text():
    snapshot = FactSnapshot(
        display_math=(
            display_math(r"A t t e n t ( Q , K , V )"),
            display_math("<!-- formula-not-decoded -->"),
        ),
        inline_math=(inline_math("cid:127 + x"),),
    )

    classified = MathHost().classify(snapshot)

    assert [(fact.reason, fact.excerpt) for fact in classified.suspicious_formulas] == [
        ("spaced_latex_tokens", "A t t e n t ( Q , K , V )"),
        ("formula_placeholder", "<!-- formula-not-decoded -->"),
        ("garbled_marker", "cid:127"),
    ]


def test_math_host_leaves_known_math_classified():
    snapshot = FactSnapshot(
        display_math=(display_math(r"x^2 + y^2 = z^2"),),
        inline_math=(inline_math(r"\alpha + \beta"),),
    )

    classified = MathHost().classify(snapshot)

    assert classified.unknown_math == ()
    assert classified.suspicious_formulas == ()


def test_math_container_engine_reports_unknown_and_multi_label_math():
    classified = MathHost().classify(
        FactSnapshot(
            display_math=(
                display_math(
                    r"\begin{align}x&=y\end{align}",
                    label_fact_ids=("label::eq-a", "label::eq-b"),
                ),
            ),
        )
    )

    diagnostics = MathContainerEngine().run(QueryHost(classified))
    by_code = {diagnostic.code: diagnostic for diagnostic in diagnostics}
    assert by_code["MATH020"].detail == r"\begin{align}"
    assert by_code["MATH021"].severity_default.value == "warning"
