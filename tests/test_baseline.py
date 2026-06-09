from __future__ import annotations

import json
from pathlib import PurePosixPath

import pytest

from scieqlint.diag.baseline import (
    apply_baseline,
    baseline_identities_from_json,
    diagnostic_identity,
)
from scieqlint.diag.model import Diagnostic, Severity, SourceSpan


def test_baseline_identity_matches_diagnostic_detail() -> None:
    diagnostic = _diagnostic(detail="left - right = 2*a*b")
    identities = baseline_identities_from_json(
        json.dumps(
            {
                "diagnostics": [
                    {
                        "code": "ALG001",
                        "path": "paper.md",
                        "line": 2,
                        "col": 1,
                        "end_line": 2,
                        "end_col": 19,
                        "detail": "left - right = 2*a*b",
                    }
                ]
            }
        )
    )

    assert diagnostic_identity(diagnostic) in identities
    assert apply_baseline((diagnostic,), identities)[0].suppressed is True


def test_baseline_keeps_nonmatching_diagnostic_unsuppressed() -> None:
    diagnostic = _diagnostic(detail="left - right = 2*a*b")
    identities = baseline_identities_from_json(
        json.dumps(
            {
                "diagnostics": [
                    {
                        "code": "ALG001",
                        "path": "paper.md",
                        "line": 2,
                        "col": 2,
                        "end_line": 2,
                        "end_col": 19,
                        "detail": "left - right = 2*a*b",
                    }
                ]
            }
        )
    )

    assert apply_baseline((diagnostic,), identities)[0].suppressed is False


def test_baseline_identity_uses_message_when_detail_is_absent() -> None:
    diagnostic = _diagnostic(detail=None)
    identities = baseline_identities_from_json(
        json.dumps(
            {
                "diagnostics": [
                    {
                        "code": "ALG001",
                        "path": "paper.md",
                        "line": 2,
                        "col": 1,
                        "end_line": 2,
                        "end_col": 19,
                        "message": "algebraic identity does not hold",
                    }
                ]
            }
        )
    )

    assert diagnostic_identity(diagnostic) in identities


def test_baseline_keeps_different_end_span_unsuppressed() -> None:
    diagnostic = _diagnostic(detail="left - right = 2*a*b")
    identities = baseline_identities_from_json(
        json.dumps(
            {
                "diagnostics": [
                    {
                        "code": "ALG001",
                        "path": "paper.md",
                        "line": 2,
                        "col": 1,
                        "end_line": 2,
                        "end_col": 18,
                        "detail": "left - right = 2*a*b",
                    }
                ]
            }
        )
    )

    assert apply_baseline((diagnostic,), identities)[0].suppressed is False


def test_baseline_rejects_malformed_diagnostics_list() -> None:
    with pytest.raises(ValueError, match="baseline diagnostics must be a list"):
        baseline_identities_from_json(json.dumps({"diagnostics": {}}))


def test_baseline_rejects_invalid_entry_type() -> None:
    with pytest.raises(ValueError, match="baseline diagnostic must be a JSON object"):
        baseline_identities_from_json(json.dumps({"diagnostics": [1]}))


def test_baseline_rejects_boolean_integer_field() -> None:
    with pytest.raises(ValueError, match="baseline diagnostic line must be an integer or null"):
        baseline_identities_from_json(
            json.dumps({"diagnostics": [{"code": "ALG001", "line": True}]})
        )


def test_baseline_rejects_out_of_range_integer_field() -> None:
    with pytest.raises(ValueError, match="baseline diagnostic col must be >= 1"):
        baseline_identities_from_json(json.dumps({"diagnostics": [{"code": "ALG001", "col": 0}]}))


def _diagnostic(*, detail: str | None) -> Diagnostic:
    return Diagnostic(
        code="ALG001",
        severity=Severity.ERROR,
        message="algebraic identity does not hold",
        span=SourceSpan(
            path=PurePosixPath("paper.md"),
            start=3,
            end=12,
            line=2,
            col=1,
            end_line=2,
            end_col=19,
        ),
        detail=detail,
    )
