from __future__ import annotations

import string
from dataclasses import fields, is_dataclass
from pathlib import PurePosixPath

from hypothesis import given, settings
from hypothesis import strategies as st

from scieqlint.diag.model import SourceSpan
from scieqlint.engine.reference import ReferenceEngine
from scieqlint.engine.structure import StructureEngine
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.markdown import parse_fence_opener
from scieqlint.query.host import QueryHost
from scieqlint.source.maps import SourceMap

PROPERTY_SETTINGS = settings(
    max_examples=40,
    derandomize=True,
    database=None,
    deadline=None,
)

_MARKDOWN_FRAGMENTS = (
    "# Heading\n",
    "(target)=\n## Anchored heading\n",
    "See {ref}`target`.\n",
    "Inline math $x + y$ and {eq}`eq-one`.\n",
    "```{math}\n:label: eq-one\nx = y\n```\n",
    "```{code-cell} python\n:label: cell-one\nprint(1)\n```\n",
    "\\begin{equation} z = 1 \\label{eq-raw} \\end{equation}\n",
    "Text with `literal $x$` and [link](chapter.md#target).\n",
    "<!-- generated: tool=test version=1 -->\n$$\na=b\n$$\n",
)


def _markdown(text: str) -> SourceDocument:
    return SourceDocument.from_text(
        PurePosixPath("property.md"),
        text,
        DocumentKind.MARKDOWN,
    )


def _source_spans(value: object) -> tuple[SourceSpan, ...]:
    if isinstance(value, SourceSpan):
        return (value,)
    if isinstance(value, tuple):
        return tuple(span for item in value for span in _source_spans(item))
    if is_dataclass(value) and not isinstance(value, type):
        return tuple(
            span for field in fields(value) for span in _source_spans(getattr(value, field.name))
        )
    return ()


@PROPERTY_SETTINGS
@given(st.lists(st.sampled_from(_MARKDOWN_FRAGMENTS), min_size=1, max_size=8))
def test_myst_fact_spans_are_valid_source_slices(fragments: list[str]) -> None:
    document = _markdown("".join(fragments))
    snapshot = MySTFrontend().lower((document,))
    source_map = SourceMap.for_document(document)

    spans = tuple(span for fact in snapshot.all_facts() for span in _source_spans(fact))
    assert spans
    for span in spans:
        assert span.path == document.path
        assert 0 <= span.start <= span.end <= len(document.text)
        assert span == source_map.span(span.start, span.end)


@PROPERTY_SETTINGS
@given(
    st.lists(st.sampled_from(_MARKDOWN_FRAGMENTS), min_size=1, max_size=8),
    st.booleans(),
)
def test_newline_normalization_preserves_facts_and_diagnostics(
    fragments: list[str],
    trailing_newline: bool,
) -> None:
    lf_text = "".join(fragments).rstrip("\n") + ("\n" if trailing_newline else "")
    lf_document = _markdown(lf_text)
    crlf_document = _markdown(lf_text.replace("\n", "\r\n"))

    assert crlf_document == lf_document
    lf_snapshot = MySTFrontend().lower((lf_document,))
    crlf_snapshot = MySTFrontend().lower((crlf_document,))
    assert crlf_snapshot == lf_snapshot

    lf_query = QueryHost(lf_snapshot)
    crlf_query = QueryHost(crlf_snapshot)
    assert StructureEngine().run(crlf_query) == StructureEngine().run(lf_query)
    assert ReferenceEngine().run(crlf_query) == ReferenceEngine().run(lf_query)


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

    source_map = SourceMap.for_document(document)
    language_start = len(prefix) + len(marker) + len("{code-cell} ")
    label_start = text.index(f":{label_key}: {label}") + len(label_key) + 3
    assert cell.language_span == source_map.span(language_start, language_start + len(language))
    assert cell.label_span == source_map.span(label_start, label_start + len(label))

    query = QueryHost(snapshot)
    assert ReferenceEngine().run(query) == ()
