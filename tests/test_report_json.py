from __future__ import annotations

import json

from scieqlint.diag.model import CheckResult
from scieqlint.report.json import JsonReporter


def test_json_report_has_stable_summary_shape() -> None:
    result = CheckResult(
        diagnostics=(),
        files_checked=1,
        math_blocks_checked=2,
        config_path=None,
        version="0.1.0",
    )
    payload = json.loads(JsonReporter().render(result))
    assert payload["schema_version"] == "0.1"
    assert payload["summary"] == {
        "errors": 0,
        "files_checked": 1,
        "info": 0,
        "math_blocks_checked": 2,
        "warnings": 0,
    }
