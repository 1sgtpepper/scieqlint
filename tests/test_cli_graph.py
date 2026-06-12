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


def test_graph_uses_project_order_and_ignore_without_paths(tmp_path) -> None:
    root = tmp_path / "book"
    root.mkdir()
    kept = root / "kept.md"
    ignored = root / "ignored.md"
    config = tmp_path / "scieqlint.toml"
    kept.write_text(
        "$$\nE = mc^2\n$$ {#kept}\n\nSee {eq}`kept`.\n",
        encoding="utf-8",
    )
    ignored.write_text(
        "$$\nF = ma\n$$ {#ignored}\n\nSee {eq}`ignored`.\n",
        encoding="utf-8",
    )
    config.write_text(
        "\n".join(
            [
                "[project]",
                'root = "book"',
                'order = ["kept.md"]',
                "",
                "[ignore]",
                'files = ["ignored.md"]',
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["graph", "--config", str(config)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert [(node["kind"], node["label"]) for node in payload["nodes"]] == [
        ("equation", "kept"),
        ("reference", "kept"),
    ]
