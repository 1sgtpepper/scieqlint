from __future__ import annotations

from pathlib import PurePosixPath

from scieqlint.diag.model import SourceSpan
from scieqlint.parse.ast import Equation, EquationGroup
from scieqlint.parse.parser import ParseOk, ParseUnknown


def test_parse_result_contracts_hold_ast_or_diagnostics() -> None:
    span = SourceSpan(PurePosixPath("paper.md"), 0, 1, 1, 1, 1, 1)
    group = EquationGroup((Equation((), span),), span)
    assert ParseOk(group).ast is group
    assert ParseUnknown("unsupported", ()).reason == "unsupported"
