from __future__ import annotations

import json

from click.testing import CliRunner

from scieqlint.cli import main


def test_graph_outputs_json_to_stdout() -> None:
    result = CliRunner().invoke(main, ["graph", "tests/fixtures/good/graph_refs.md"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "0.3"
    assert [node["kind"] for node in payload["nodes"]] == [
        "equation",
        "equation",
        "reference",
        "reference",
        "reference",
    ]
    assert {span["path"] for span in (node["span"] for node in payload["nodes"])} == {
        "tests/fixtures/good/graph_refs.md"
    }


def test_graph_writes_output_file(tmp_path) -> None:
    output = tmp_path / "graph.json"

    result = CliRunner().invoke(
        main,
        ["graph", "tests/fixtures/good/graph_refs.md", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert result.output == ""
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "0.3"
    assert len(payload["edges"]) == 3
