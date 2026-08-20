from __future__ import annotations

import string
from pathlib import PurePosixPath

from hypothesis import given, settings
from hypothesis import strategies as st

from scieqlint.diag.model import SourceSpan
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.markdown import parse_fence_opener
from scieqlint.query.host import QueryHost

PROPERTY_SETTINGS = settings(
    max_examples=40,
    derandomize=True,
    database=None,
    deadline=None,
)

_SOURCE_TOKEN_CASES = (
    ("heading", "# Heading\n"),
    ("anchor", "(target)=\n"),
    ("reference", "See {ref}`target`.\n"),
    ("inline_math", "Inline math $x + y$.\n"),
)


def _markdown(text: str) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("property.md"),
        text,
        DocumentKind.MARKDOWN,
    )


def _span_text(document: SourceDocument, span: SourceSpan | None) -> str:
    assert span is not None
    assert span.path == document.path
    assert 0 <= span.start <= span.end <= len(document.text)
    return document.text[span.start : span.end]


@PROPERTY_SETTINGS
@given(st.lists(st.sampled_from(_SOURCE_TOKEN_CASES), min_size=1, max_size=8))
def test_myst_fact_spans_select_their_source_tokens(
    token_cases: list[tuple[str, str]],
) -> None:
    document = _markdown("".join(text for _name, text in token_cases))
    snapshot = MySTFrontend().lower((document,))
    expected = {
        "heading": [text for name, text in token_cases if name == "heading"],
        "anchor": [text for name, text in token_cases if name == "anchor"],
        "reference": ["{ref}`target`" for name, _text in token_cases if name == "reference"],
        "inline_math": ["x + y" for name, _text in token_cases if name == "inline_math"],
    }

    assert [_span_text(document, fact.span) for fact in snapshot.headings] == expected[
        "heading"
    ]
    assert [_span_text(document, fact.span) for fact in snapshot.target_anchors] == expected[
        "anchor"
    ]
    assert [_span_text(document, fact.span) for fact in snapshot.generic_refs] == expected[
        "reference"
    ]
    assert [_span_text(document, fact.span) for fact in snapshot.inline_math] == expected[
        "inline_math"
    ]


@PROPERTY_SETTINGS
@given(
    st.builds(
        lambda first, tail: first + tail,
        st.sampled_from(tuple(string.ascii_lowercase)),
        st.text(alphabet=string.ascii_lowercase + string.digits + "-", max_size=8),
    ),
    st.sampled_from(("\n", "\r\n", "\r")),
)
def test_raw_newline_ingress_preserves_reference_semantics(
    label: str,
    newline: str,
) -> None:
    raw_text = (
        f"```{{math}}{newline}"
        f":label: {label}{newline}"
        f"x = y{newline}"
        f"```{newline}{newline}"
        f"See {{eq}}`{label}`.{newline}"
    )
    document = _markdown(raw_text)
    snapshot = MySTFrontend().lower((document,))

    [equation_label] = snapshot.equation_labels
    [equation_ref] = snapshot.equation_refs
    assert equation_label.normalized_label == label
    assert equation_ref.normalized_target == label
    assert _span_text(document, equation_label.label_span) == label
    assert _span_text(document, equation_ref.target_span) == label

    query = QueryHost(snapshot)
    assert query.references.equation_target_index() == {label: (equation_label,)}
    assert query.references.unresolved_equation_refs() == ()
    assert ReferenceEngine().run(query) == ()


@st.composite
def _code_cell_cases(draw) -> tuple[str, str, str, str, int]:
    fence_char = draw(st.sampled_from(("`", "~")))
    fence_length = draw(st.integers(min_value=3, max_value=6))
    first_language = draw(st.sampled_from(tuple(string.ascii_letters)))
    language_tail = draw(
        st.text(
            alphabet=string.ascii_letters + string.digits + "_.+-",
            min_size=0,
            max_size=10,
        )
    )
    first_label = draw(st.sampled_from(tuple(string.ascii_lowercase)))
    label_tail = draw(
        st.text(
            alphabet=string.ascii_lowercase + string.digits + "_-",
            min_size=0,
            max_size=10,
        )
    )
    label_key = draw(st.sampled_from(("label", "name")))
    indent = draw(st.integers(min_value=0, max_value=3))
    return (
        fence_char * fence_length,
        first_language + language_tail,
        first_label + label_tail,
        label_key,
        indent,
    )


@PROPERTY_SETTINGS
@given(_code_cell_cases())
def test_code_cell_fence_scanner_and_frontend_agree(
    case: tuple[str, str, str, str, int],
) -> None:
    marker, language, label, label_key, indent = case
    prefix = " " * indent
    opener = f"{prefix}{marker}{{code-cell}} {language}"
    text = (
        f"{opener}\n"
        f":{label_key}: {label}\n"
        "raise RuntimeError('property tests never execute cells')\n"
        f"{prefix}{marker}\n\n"
        f"See {{ref}}`{label}`.\n"
    )
    document = _markdown(text)

    assert parse_fence_opener(opener) == (marker, f"{{code-cell}} {language}")
    snapshot = MySTFrontend().lower((document,))
    [cell] = snapshot.code_cells
    assert cell.language == language
    assert cell.label == label
    assert cell.normalized_label == label

    language_start = len(prefix) + len(marker) + len("{code-cell} ")
    label_start = text.index(f":{label_key}: {label}") + len(label_key) + 3
    assert cell.language_span is not None
    assert cell.label_span is not None
    assert cell.language_span.start == language_start
    assert cell.label_span.start == label_start
    assert _span_text(document, cell.language_span) == language
    assert _span_text(document, cell.label_span) == label

    query = QueryHost(snapshot)
    [reference] = snapshot.generic_refs
    assert reference.normalized_target == label
    assert _span_text(document, reference.target_span) == label
    assert query.references.target_index()[label] == (cell,)
    assert ReferenceEngine().run(query) == ()
