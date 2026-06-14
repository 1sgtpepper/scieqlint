from dataclasses import FrozenInstanceError
from pathlib import PurePosixPath
from typing import Any

import pytest

from scieqlint.facts.math import InlineMathFact
from scieqlint.facts.snapshot import FactSnapshot
from scieqlint.io.source import DocumentKind, SourceDocument


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
