from __future__ import annotations

from scieqlint.diag.model import CheckResult
from scieqlint.report.text import TextReporter


def test_empty_text_report_names_checked_counts() -> None:
    result = CheckResult(
        diagnostics=(),
        files_checked=2,
        math_blocks_checked=3,
        config_path=None,
        version="0.1.0",
    )
    rendered = TextReporter().render(result)
    assert "found no diagnostics" in rendered
    assert "files checked: 2" in rendered
    assert "math blocks checked: 3" in rendered
