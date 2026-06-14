from dataclasses import FrozenInstanceError
from pathlib import PurePosixPath
from typing import Any

import pytest

from scieqlint.facts.math import InlineMathFact, UnknownMathFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.io.source import DocumentKind, SourceDocument
from scieqlint.source.maps import SourceMap


def doc(path: str, text: str) -> SourceDocument:
    return SourceDocument.from_text(PurePosixPath(path), text, DocumentKind.MARKDOWN)


def mutate_inline_body(inline: Any) -> None:
    inline.body = "y"


def test_fact_snapshot_is_deterministic_and_immutable():
    document = doc("a.md", "# Title\n\nText $x$.\n")
    inline = InlineMathFact(
        fact_id="a.md::inline-math::16",
        document_id="a.md",
        span=None,
        raw="$x$",
        body="x",
        delimiter_kind="dollar",
        context="paragraph",
    )

    snapshot = FactSnapshot(documents=(document,), inline_math=(inline,))

    assert snapshot == FactSnapshot(documents=(document,), inline_math=(inline,))
    assert snapshot.documents[0].path.as_posix() == "a.md"
    assert snapshot.all_facts() == (inline,)
    with pytest.raises(FrozenInstanceError):
        mutate_inline_body(inline)


def test_source_map_spans_use_document_offsets():
    document = doc("chapter.md", "alpha\nbeta\n")
    source_map = SourceMap.for_document(document)

    span = source_map.span(6, 10)

    assert source_map.identity.document_id == "chapter.md"
    assert source_map.identity.kind == DocumentKind.MARKDOWN.value
    assert span.path.as_posix() == "chapter.md"
    assert (span.start, span.end) == (6, 10)
    assert (span.line, span.col, span.end_line, span.end_col) == (2, 1, 2, 4)
    with pytest.raises(ValueError, match="invalid span offsets"):
        source_map.span(5, 4)


def test_snapshot_with_unknown_math_appends_without_mutating_original():
    document = doc("a.md", "Text $x$.\n")
    inline = InlineMathFact(
        fact_id="a.md::inline-math::6",
        document_id="a.md",
        span=None,
        raw="$x$",
        body="x",
        delimiter_kind="dollar",
        context="paragraph",
    )
    unknown = UnknownMathFact(
        fact_id="a.md::unknown-math::6",
        document_id="a.md",
        span=None,
        raw="$x$",
        source_math_fact_id=inline.fact_id,
        reason="macro",
        excerpt=r"\newcommand",
    )

    snapshot = FactSnapshot(documents=(document,), inline_math=(inline,))
    updated = snapshot.with_unknown_math((unknown,))

    assert snapshot.unknown_math == ()
    assert updated.inline_math == (inline,)
    assert updated.unknown_math == (unknown,)
    assert updated.all_facts() == (inline, unknown)
