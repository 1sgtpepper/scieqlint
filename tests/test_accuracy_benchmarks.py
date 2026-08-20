from __future__ import annotations

import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import cast

import pytest

from scieqlint.api import check_documents
from scieqlint.config.load import load_config
from scieqlint.diag.catalog import CATALOG
from scieqlint.io.source import DocumentKind, SourceDocument

CORPUS_PATH = Path("benchmarks/accuracy/corpus-v1.json")
_FORMAT_VERSION = 1
_TOP_LEVEL_FIELDS = frozenset({"format_version", "cases"})
_CASE_FIELDS = frozenset(
    {
        "id",
        "release",
        "label",
        "rule",
        "source_format",
        "scientific_domain",
        "provenance",
        "license",
        "synthetic",
        "documents",
        "config",
        "expected_codes",
        "expected_pass",
    }
)
_OPTIONAL_CASE_FIELDS = frozenset({"independent_equation_id"})
_DOCUMENT_FIELDS = frozenset({"path", "format", "content"})
_CONFIG_FIELDS = frozenset(
    {
        "dimension_variables",
        "unknown_variables",
        "profile",
        "missing_label_strict",
        "inline_math",
        "symbols",
    }
)
_OPTIONAL_CONFIG_FIELDS = frozenset({"output_profile"})
_SOURCE_FORMATS = frozenset({"markdown", "latex", "notebook"})
_PROFILE_NAMES = frozenset(
    {
        "generated-myst",
        "cross-format-references",
        "math-accessibility",
        "notebook-crossrefs",
        "reference-display",
        "typst-portability",
        "code-cell-metadata",
    }
)
_OUTPUT_PROFILES = frozenset({"commonmark", "myst", "notebook", "typst"})
_INDEPENDENT_EQUATION_THRESHOLD = 100
_CASE_ID_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


def test_accuracy_corpus_is_strict_versioned_and_balanced() -> None:
    assert CORPUS_PATH.is_file()
    assert list(CORPUS_PATH.parent.glob("*.yml")) == []
    cases = _load_corpus(CORPUS_PATH)

    assert len(cases) >= 48

    labels_by_rule: dict[str, set[str]] = {}
    for case in cases:
        labels_by_rule.setdefault(cast(str, case["rule"]), set()).add(cast(str, case["label"]))
    assert len(labels_by_rule) >= 20
    assert all(labels == {"positive", "negative"} for labels in labels_by_rule.values())
    assert {cast(str, case["source_format"]) for case in cases} == {
        "markdown",
        "latex",
        "notebook",
    }


def test_synthetic_wrappers_do_not_count_as_independent_equations(tmp_path: Path) -> None:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    source_case = cast(dict[str, object], payload["cases"][0])
    first = dict(source_case, id="synthetic-equation-one")
    second = dict(source_case, id="synthetic-equation-two")
    path = tmp_path / "synthetic-wrappers.json"
    path.write_text(
        json.dumps({"format_version": _FORMAT_VERSION, "cases": [first, second]}),
        encoding="utf-8",
    )

    assert _independent_equation_ids(_load_corpus(path)) == set()


def test_independent_equation_ids_deduplicate_labeled_wrappers(tmp_path: Path) -> None:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    source_case = cast(dict[str, object], payload["cases"][0])
    first = dict(
        source_case,
        id="independent-equation-one",
        license="CC0-1.0",
        synthetic=False,
        independent_equation_id="equation-one",
    )
    second = dict(first, id="independent-equation-one-wrapper")
    path = tmp_path / "labeled-wrappers.json"
    path.write_text(
        json.dumps({"format_version": _FORMAT_VERSION, "cases": [first, second]}),
        encoding="utf-8",
    )

    assert _independent_equation_ids(_load_corpus(path)) == {"equation-one"}


def test_synthetic_cases_cannot_claim_independent_equation_ids(tmp_path: Path) -> None:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    source_case = cast(dict[str, object], payload["cases"][0])
    case = dict(source_case, independent_equation_id="equation-one")
    path = tmp_path / "synthetic-independent-id.json"
    path.write_text(
        json.dumps({"format_version": _FORMAT_VERSION, "cases": [case]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="synthetic cases cannot claim independent_equation_id"):
        _load_corpus(path)


def test_non_synthetic_cases_require_an_independent_equation_id(tmp_path: Path) -> None:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    source_case = cast(dict[str, object], payload["cases"][0])
    case = dict(source_case, license="CC0-1.0", synthetic=False)
    path = tmp_path / "missing-independent-id.json"
    path.write_text(
        json.dumps({"format_version": _FORMAT_VERSION, "cases": [case]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="requires independent_equation_id"):
        _load_corpus(path)


def test_every_accuracy_case_runs_through_public_analysis(tmp_path: Path) -> None:
    for case in _load_corpus(CORPUS_PATH):
        result = _check_case(tmp_path, case)
        actual_codes = [diagnostic.code for diagnostic in result.diagnostics]

        assert actual_codes == case["expected_codes"], case["id"]
        assert (result.exit_code() == 0) is case["expected_pass"], case["id"]
        if case.get("independent_equation_id") is not None:
            assert result.math_blocks_checked > 0, case["id"]


def test_schema_rejects_profile_without_required_output_configuration(tmp_path: Path) -> None:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    source_case = cast(dict[str, object], payload["cases"][0])
    config = dict(cast(dict[str, object], source_case["config"]))
    config["profile"] = "cross-format-references"
    case = dict(source_case, config=config)
    path = tmp_path / "invalid-profile.json"
    path.write_text(
        json.dumps({"format_version": _FORMAT_VERSION, "cases": [case]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="requires output_profile"):
        _load_corpus(path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "accuracy case 0 missing fields: expected_pass"),
        ("unknown", "accuracy case 0 has unknown fields: surprise"),
    ],
)
def test_accuracy_corpus_rejects_missing_and_unknown_case_fields(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    first = payload["cases"][0]
    if mutation == "missing":
        first.pop("expected_pass")
    else:
        first["surprise"] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=re.escape(message)):
        _load_corpus(path)


@pytest.mark.parametrize(
    ("container", "mutation", "message"),
    [
        ("document", "missing", "accuracy case 0 document 0 missing fields: content"),
        ("document", "unknown", "accuracy case 0 document 0 has unknown fields: mode"),
        ("config", "missing", "accuracy case 0 config missing fields: symbols"),
        ("config", "unknown", "accuracy case 0 config has unknown fields: timeout"),
    ],
)
def test_accuracy_corpus_rejects_nested_schema_drift(
    tmp_path: Path,
    container: str,
    mutation: str,
    message: str,
) -> None:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    target = (
        payload["cases"][0]["documents"][0]
        if container == "document"
        else payload["cases"][0]["config"]
    )
    field = "content" if container == "document" else "symbols"
    unknown = "mode" if container == "document" else "timeout"
    if mutation == "missing":
        target.pop(field)
    else:
        target[unknown] = "unexpected"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=re.escape(message)):
        _load_corpus(path)


def test_accuracy_corpus_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    payload["cases"][1]["id"] = payload["cases"][0]["id"]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate accuracy case id: polynomial-good-square"):
        _load_corpus(path)


def test_accuracy_corpus_rejects_unknown_top_level_fields(tmp_path: Path) -> None:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    payload["metadata"] = {}
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="accuracy corpus has unknown fields: metadata"):
        _load_corpus(path)


def test_accuracy_corpus_rejects_duplicate_json_fields(tmp_path: Path) -> None:
    text = CORPUS_PATH.read_text(encoding="utf-8").replace(
        '"format_version": 1,',
        '"format_version": 1, "format_version": 1,',
        1,
    )
    path = tmp_path / "invalid.json"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate JSON field: format_version"):
        _load_corpus(path)


@pytest.mark.skipif(
    os.environ.get("SCIEQLINT_RELEASE_GATE") != "1",
    reason="stable-release evidence is enforced by the release workflow",
)
def test_stable_release_requires_100_independently_labeled_equations() -> None:
    cases = _load_corpus(CORPUS_PATH)
    independent_equation_ids = _independent_equation_ids(cases)

    assert len(independent_equation_ids) >= _INDEPENDENT_EQUATION_THRESHOLD, (
        "stable releases require at least 100 independently labeled semantic equations; "
        f"found {len(independent_equation_ids)}"
    )


def _check_case(tmp_path: Path, case: dict[str, object]):
    documents: list[SourceDocument] = []
    for raw_document in cast(list[dict[str, object]], case["documents"]):
        source_format = cast(str, raw_document["format"])
        content = raw_document["content"]
        text = (
            json.dumps(content, sort_keys=True)
            if source_format == "notebook"
            else cast(str, content)
        )
        documents.append(
            SourceDocument.from_text(
                PurePosixPath(f"benchmarks/accuracy/{raw_document['path']}"),
                text,
                DocumentKind(source_format),
            )
        )
    return check_documents(documents, config=_case_config(tmp_path, case))


def _case_config(tmp_path: Path, case: dict[str, object]):
    data = cast(dict[str, object], case["config"])
    variables = cast(dict[str, str], data["dimension_variables"])
    lines = [
        "[checks.dimension]",
        'mode = "auto"',
        f'unknown_variables = "{data["unknown_variables"]}"',
        "",
        "[checks.references]",
        f"missing_label_strict = {str(data['missing_label_strict']).lower()}",
        "",
        "[checks.symbols]",
        f"enabled = {str(data['symbols']).lower()}",
        "",
        "[scanner]",
        f"inline_math = {str(data['inline_math']).lower()}",
    ]
    profile = data["profile"]
    output_profile = data.get("output_profile")
    if profile is not None:
        lines.extend(("", "[profile]", f'name = "{profile}"'))
        if output_profile is not None:
            lines.append(f'output_profile = "{output_profile}"')
    if variables:
        lines.extend(("", "[vars]"))
        lines.extend(f'{name} = "{dimension}"' for name, dimension in sorted(variables.items()))
    config_path = tmp_path / f"{case['id']}.toml"
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return load_config(config_path)


def _load_corpus(path: Path) -> list[dict[str, object]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid accuracy corpus JSON: {exc.msg}") from exc
    if not isinstance(raw, dict):
        raise ValueError("accuracy corpus must be a JSON object")
    _require_exact_fields(raw, _TOP_LEVEL_FIELDS, "accuracy corpus")
    if type(raw["format_version"]) is not int or raw["format_version"] != _FORMAT_VERSION:
        raise ValueError(
            f"accuracy corpus format_version must be {_FORMAT_VERSION}, "
            f"got {raw['format_version']!r}"
        )
    raw_cases = raw["cases"]
    if not isinstance(raw_cases, list):
        raise ValueError("accuracy corpus cases must be a JSON array")

    cases: list[dict[str, object]] = []
    case_ids: set[str] = set()
    for index, raw_case in enumerate(raw_cases):
        if not isinstance(raw_case, dict):
            raise ValueError(f"accuracy case {index} must be a JSON object")
        _validate_case(raw_case, index)
        case_id = cast(str, raw_case["id"])
        if case_id in case_ids:
            raise ValueError(f"duplicate accuracy case id: {case_id}")
        case_ids.add(case_id)
        cases.append(raw_case)
    return cases


def _validate_case(case: dict[str, object], index: int) -> None:
    context = f"accuracy case {index}"
    _require_exact_fields(case, _CASE_FIELDS, context, optional=_OPTIONAL_CASE_FIELDS)
    case_id = _require_string(case["id"], f"{context} id")
    if _CASE_ID_RE.fullmatch(case_id) is None:
        raise ValueError(f"{context} id must be a lowercase hyphenated identifier")
    _require_string(case["release"], f"{context} release")
    label = _require_choice(case["label"], {"positive", "negative"}, f"{context} label")
    rule = _require_string(case["rule"], f"{context} rule")
    if rule not in CATALOG:
        raise ValueError(f"{context} rule is not in the diagnostic catalog: {rule}")
    source_format = _require_choice(
        case["source_format"], _SOURCE_FORMATS, f"{context} source_format"
    )
    _require_string(case["scientific_domain"], f"{context} scientific_domain")
    _require_string(case["provenance"], f"{context} provenance")
    synthetic = _require_bool(case["synthetic"], f"{context} synthetic")
    license_name = case["license"]
    if synthetic:
        if license_name is not None:
            raise ValueError(f"{context} synthetic cases must use a null license")
    else:
        _require_string(license_name, f"{context} license")
    independent_equation_id = case.get("independent_equation_id")
    if independent_equation_id is None:
        if not synthetic:
            raise ValueError(
                f"{context} non-synthetic cases require independent_equation_id"
            )
    else:
        if synthetic:
            raise ValueError(
                f"{context} synthetic cases cannot claim independent_equation_id"
            )
        independent_id = _require_string(
            independent_equation_id,
            f"{context} independent_equation_id",
        )
        if _CASE_ID_RE.fullmatch(independent_id) is None:
            raise ValueError(
                f"{context} independent_equation_id must be a lowercase hyphenated identifier"
            )

    documents = case["documents"]
    if not isinstance(documents, list) or not documents:
        raise ValueError(f"{context} documents must be a non-empty JSON array")
    for document_index, document in enumerate(documents):
        _validate_document(document, context, document_index)
    first_document = cast(dict[str, object], documents[0])
    if first_document["format"] != source_format:
        raise ValueError(f"{context} source_format must match the first document")

    _validate_config(case["config"], context)
    expected_codes = case["expected_codes"]
    if not isinstance(expected_codes, list) or not all(
        isinstance(code, str) and code in CATALOG for code in expected_codes
    ):
        raise ValueError(f"{context} expected_codes must contain catalog codes")
    if (rule in expected_codes) is not (label == "positive"):
        raise ValueError(f"{context} label does not match the expected result for {rule}")
    _require_bool(case["expected_pass"], f"{context} expected_pass")


def _validate_document(value: object, context: str, index: int) -> None:
    document_context = f"{context} document {index}"
    if not isinstance(value, dict):
        raise ValueError(f"{document_context} must be a JSON object")
    _require_exact_fields(value, _DOCUMENT_FIELDS, document_context)
    _require_string(value["path"], f"{document_context} path")
    source_format = _require_choice(value["format"], _SOURCE_FORMATS, f"{document_context} format")
    content = value["content"]
    if source_format == "notebook":
        if not isinstance(content, dict):
            raise ValueError(f"{document_context} notebook content must be an object")
    elif not isinstance(content, str):
        raise ValueError(f"{document_context} content must be a string")


def _validate_config(value: object, context: str) -> None:
    config_context = f"{context} config"
    if not isinstance(value, dict):
        raise ValueError(f"{config_context} must be a JSON object")
    _require_exact_fields(value, _CONFIG_FIELDS, config_context, optional=_OPTIONAL_CONFIG_FIELDS)
    variables = value["dimension_variables"]
    if not isinstance(variables, dict) or not all(
        isinstance(name, str) and isinstance(dimension, str)
        for name, dimension in variables.items()
    ):
        raise ValueError(f"{config_context} dimension_variables must map strings to strings")
    _require_choice(
        value["unknown_variables"],
        {"warn", "ignore"},
        f"{config_context} unknown_variables",
    )
    profile = value["profile"]
    if profile is not None:
        _require_choice(profile, _PROFILE_NAMES, f"{config_context} profile")
    output_profile = value.get("output_profile")
    if output_profile is not None:
        _require_choice(output_profile, _OUTPUT_PROFILES, f"{config_context} output_profile")
    if profile == "cross-format-references" and output_profile is None:
        raise ValueError(
            f"{config_context} profile cross-format-references requires output_profile"
        )
    if profile != "cross-format-references" and output_profile is not None:
        raise ValueError(
            f"{config_context} output_profile is only valid for cross-format-references"
        )
    _require_bool(value["missing_label_strict"], f"{config_context} missing_label_strict")
    _require_bool(value["inline_math"], f"{config_context} inline_math")
    _require_bool(value["symbols"], f"{config_context} symbols")


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _require_exact_fields(
    value: dict[str, object],
    expected: frozenset[str],
    context: str,
    *,
    optional: frozenset[str] = frozenset(),
) -> None:
    actual = frozenset(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected - optional)
    if missing:
        raise ValueError(f"{context} missing fields: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"{context} has unknown fields: {', '.join(unknown)}")


def _require_string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty string")
    return value


def _require_choice(value: object, choices: set[str] | frozenset[str], context: str) -> str:
    text = _require_string(value, context)
    if text not in choices:
        raise ValueError(f"{context} must be one of: {', '.join(sorted(choices))}")
    return text


def _require_bool(value: object, context: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{context} must be a boolean")
    return value


def _independent_equation_ids(cases: list[dict[str, object]]) -> set[str]:
    return {
        cast(str, case["independent_equation_id"])
        for case in cases
        if case.get("independent_equation_id") is not None
    }
