from pathlib import Path

from scieqlint.api_architecture import analyze_paths_architecture
from scieqlint.schema.json_architecture import render_analysis_result_json


def test_architecture_api_loads_paths_and_renders_json(tmp_path: Path):
    source = tmp_path / "lecture.md"
    source.write_text("####Title\n", encoding="utf-8")
    result = analyze_paths_architecture((source,), profiles=("scientific-myst",))
    rendered = render_analysis_result_json(result)
    assert "STR001" in rendered
    assert '"schema_version": "0.2-architecture-preview"' in rendered
