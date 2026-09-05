from __future__ import annotations

import string
from pathlib import PurePosixPath

from hypothesis import example, given, settings
from hypothesis import strategies as st

from scieqlint.diag.model import SourceSpan
from scieqlint.frontend.myst import MySTFrontend
from scieqlint.io.source import DocumentKind, SourceDocument
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


def _span_offsets(document: SourceDocument, span: SourceSpan | None) -> tuple[int, int]:
    _span_text(document, span)
    assert span is not None
    return span.start, span.end


def _assert_span_coordinates(text: str, span: SourceSpan | None) -> None:
    assert span is not None
    assert 0 <= span.start <= span.end <= len(text)
    end_offset = max(span.start, span.end - 1)
    start_line_start = text.rfind("\n", 0, span.start) + 1
    end_line_start = text.rfind("\n", 0, end_offset) + 1
    assert (span.line, span.col, span.end_line, span.end_col) == (
        text.count("\n", 0, span.start) + 1,
        span.start - start_line_start + 1,
        text.count("\n", 0, end_offset) + 1,
        end_offset - end_line_start + 1,
    )


@PROPERTY_SETTINGS
@example(
    [
        ("reference", "See {ref}`target`.\n"),
        ("reference", "See {ref}`target`.\n"),
    ]
)
@given(st.lists(st.sampled_from(_SOURCE_TOKEN_CASES), min_size=1, max_size=8))
def test_myst_fact_spans_select_their_source_tokens(
    token_cases: list[tuple[str, str]],
) -> None:
    document = _markdown("".join(text for _name, text in token_cases))
    snapshot = MySTFrontend().lower((document,))
    expected_spans: dict[str, list[tuple[tuple[int, int], str]]] = {
        "heading": [],
        "heading_marker": [],
        "heading_text": [],
        "anchor": [],
        "anchor_label": [],
        "reference": [],
        "reference_role": [],
        "reference_target": [],
        "inline_math": [],
    }
    source_offset = 0
    for name, text in token_cases:
        if name == "heading":
            expected_spans[name].append(((source_offset, source_offset + len(text)), "# Heading\n"))
            marker_start = source_offset + text.index("#")
            expected_spans["heading_marker"].append(((marker_start, marker_start + 1), "#"))
            heading_text = "Heading"
            heading_text_start = source_offset + text.index(heading_text)
            expected_spans["heading_text"].append(
                ((heading_text_start, heading_text_start + len(heading_text)), heading_text)
            )
        elif name == "anchor":
            expected_spans[name].append(((source_offset, source_offset + len(text)), "(target)=\n"))
            anchor_label = "target"
            anchor_label_start = source_offset + text.index(anchor_label)
            expected_spans["anchor_label"].append(
                ((anchor_label_start, anchor_label_start + len(anchor_label)), anchor_label)
            )
        elif name == "reference":
            token = "{ref}`target`"
            start = source_offset + text.index(token)
            expected_spans[name].append(((start, start + len(token)), token))
            expected_spans["reference_role"].append(((start, start + len(token)), token))
            target = "target"
            target_start = source_offset + text.index(target)
            expected_spans["reference_target"].append(
                ((target_start, target_start + len(target)), target)
            )
        else:
            body = "x + y"
            start = source_offset + text.index(body)
            expected_spans[name].append(((start, start + len(body)), body))
        source_offset += len(text)

    assert [
        (_span_offsets(document, fact.span), _span_text(document, fact.span))
        for fact in snapshot.headings
    ] == expected_spans["heading"]
    assert [
        (_span_offsets(document, fact.marker_span), _span_text(document, fact.marker_span))
        for fact in snapshot.headings
    ] == expected_spans["heading_marker"]
    assert [
        (_span_offsets(document, fact.text_span), _span_text(document, fact.text_span))
        for fact in snapshot.headings
    ] == expected_spans["heading_text"]
    assert [
        (_span_offsets(document, fact.span), _span_text(document, fact.span))
        for fact in snapshot.target_anchors
    ] == expected_spans["anchor"]
    assert [
        (_span_offsets(document, fact.label_span), _span_text(document, fact.label_span))
        for fact in snapshot.target_anchors
    ] == expected_spans["anchor_label"]
    assert [
        (_span_offsets(document, fact.span), _span_text(document, fact.span))
        for fact in snapshot.generic_refs
    ] == expected_spans["reference"]
    assert [
        (_span_offsets(document, fact.role_span), _span_text(document, fact.role_span))
        for fact in snapshot.generic_refs
    ] == expected_spans["reference_role"]
    assert [
        (_span_offsets(document, fact.target_span), _span_text(document, fact.target_span))
        for fact in snapshot.generic_refs
    ] == expected_spans["reference_target"]
    assert [
        (_span_offsets(document, fact.span), _span_text(document, fact.span))
        for fact in snapshot.inline_math
    ] == expected_spans["inline_math"]
    for fact in snapshot.headings:
        _assert_span_coordinates(document.text, fact.span)
        _assert_span_coordinates(document.text, fact.marker_span)
        _assert_span_coordinates(document.text, fact.text_span)
    for fact in snapshot.target_anchors:
        _assert_span_coordinates(document.text, fact.span)
        _assert_span_coordinates(document.text, fact.label_span)
    for fact in snapshot.generic_refs:
        _assert_span_coordinates(document.text, fact.span)
        _assert_span_coordinates(document.text, fact.role_span)
        _assert_span_coordinates(document.text, fact.target_span)
    for fact in snapshot.inline_math:
        _assert_span_coordinates(document.text, fact.span)


@PROPERTY_SETTINGS
@given(
    st.builds(
        lambda prefix, first, tail: prefix + first + tail,
        st.sampled_from(("", "#")),
        st.sampled_from(tuple(string.ascii_lowercase)),
        st.text(alphabet=string.ascii_lowercase + string.digits + "-", max_size=8),
    ),
    st.sampled_from(("\n", "\r\n", "\r")),
)
def test_raw_newline_ingress_preserves_reference_semantics(
    label: str,
    newline: str,
) -> None:
    canonical_text = f"```{{math}}\n:label: {label}\nx = y\n```\n\nSee {{eq}}`{label}`.\n"
    raw_text = canonical_text.replace("\n", newline)
    document = _markdown(raw_text)
    assert document.text == canonical_text

    snapshot = MySTFrontend().lower((document,))

    [equation_label] = snapshot.equation_labels
    [equation_ref] = snapshot.equation_refs
    normalized_label = label.removeprefix("#")
    assert equation_label.label == label
    assert equation_ref.target == label
    assert equation_label.normalized_label == normalized_label
    assert equation_ref.normalized_target == normalized_label
    label_start = canonical_text.index(f":label: {label}") + len(":label: ")
    reference_start = canonical_text.index(f"{{eq}}`{label}`") + len("{eq}`")
    assert _span_offsets(document, equation_label.label_span) == (
        label_start,
        label_start + len(label),
    )
    assert _span_text(document, equation_label.label_span) == label
    assert _span_offsets(document, equation_ref.target_span) == (
        reference_start,
        reference_start + len(label),
    )
    assert _span_text(document, equation_ref.target_span) == label
    _assert_span_coordinates(document.text, equation_label.label_span)
    _assert_span_coordinates(document.text, equation_ref.target_span)

    query = QueryHost(snapshot)
    assert query.references.equation_target_index() == {normalized_label: (equation_label,)}
    assert query.references.unresolved_equation_refs() == ()


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
    label_prefix = draw(st.sampled_from(("", "#")))
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
        label_prefix + first_label + label_tail,
        label_key,
        indent,
    )


@PROPERTY_SETTINGS
@given(_code_cell_cases())
def test_code_cell_frontend_preserves_fence_and_reference_semantics(
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

    snapshot = MySTFrontend().lower((document,))
    [fence] = snapshot.fences
    close_line = f"{prefix}{marker}\n"
    opener_end = len(opener) + 1
    body_start = opener_end
    close_start = text.index(close_line, body_start)
    close_end = close_start + len(close_line)
    assert fence.opener == marker
    assert fence.fence_char == marker[0]
    assert fence.fence_length == len(marker)
    assert fence.info_string == f"{{code-cell}} {language}"
    assert fence.language == language
    assert fence.kind == "code-cell"
    assert fence.is_closed
    assert _span_offsets(document, fence.span) == (0, close_end)
    assert _span_offsets(document, fence.opener_span) == (0, opener_end)
    assert _span_offsets(document, fence.body_span) == (body_start, close_start)
    assert fence.closer_span is not None
    assert _span_offsets(document, fence.closer_span) == (close_start, close_end)
    assert _span_text(document, fence.span) == text[:close_end]
    assert _span_text(document, fence.opener_span) == opener + "\n"
    assert _span_text(document, fence.body_span) == (
        f":{label_key}: {label}\nraise RuntimeError('property tests never execute cells')\n"
    )
    assert _span_text(document, fence.closer_span) == close_line
    _assert_span_coordinates(document.text, fence.span)
    _assert_span_coordinates(document.text, fence.opener_span)
    _assert_span_coordinates(document.text, fence.body_span)
    _assert_span_coordinates(document.text, fence.closer_span)
    [cell] = snapshot.code_cells
    assert cell.language == language
    assert cell.label == label
    normalized_label = label.removeprefix("#")
    assert cell.normalized_label == normalized_label

    query = QueryHost(snapshot)
    [reference] = snapshot.generic_refs
    assert reference.role_kind == "ref"
    assert reference.target == label
    assert reference.normalized_target == normalized_label
    reference_start = document.text.index(f"{{ref}}`{label}`") + len("{ref}`")
    assert _span_offsets(document, reference.target_span) == (
        reference_start,
        reference_start + len(label),
    )
    assert _span_text(document, reference.target_span) == label
    _assert_span_coordinates(document.text, reference.target_span)
    assert query.references.target_index()[normalized_label] == (cell,)
    assert query.references.unresolved_generic_refs() == ()
