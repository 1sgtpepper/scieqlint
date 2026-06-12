from __future__ import annotations

from importlib import resources


def test_runtime_package_resources_are_packaged() -> None:
    expected = {
        "scieqlint": ["py.typed"],
        "scieqlint.examples.bad": ["famous_bad.md"],
        "scieqlint.examples.good": ["algebra_good.md"],
        "scieqlint.parse": ["grammar.lark"],
        "scieqlint.presets": ["mechanics.toml"],
        "scieqlint.schemas": [
            "scieqlint-diagnostic-0.1.schema.json",
            "scieqlint-graph-0.3.schema.json",
            "scieqlint-result-0.1.schema.json",
        ],
    }

    for package, names in expected.items():
        package_files = resources.files(package)
        for name in names:
            assert package_files.joinpath(name).is_file(), f"{package}:{name}"
