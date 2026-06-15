# Architecture map for contributors

| Goal | Start here | Avoid touching |
|---|---|---|
| CLI command behavior | `src/scieqlint/cli.py` | scanner/parser/checker internals |
| Config defaults | `src/scieqlint/config/` | reporters |
| Source locations | `src/scieqlint/io/source.py` | algebra |
| Markdown extraction | `src/scieqlint/scan/markdown.py` | parser/checkers |
| Grammar | `src/scieqlint/parse/grammar.lark` | reporters |
| Algebra | `src/scieqlint/check/algebra.py` | scanner |
| References | `src/scieqlint/check/references.py` | algebra |
| Generated-output anchor audits | `src/scieqlint/facts/generated.py`, `src/scieqlint/query/generated.py`, `src/scieqlint/engine/generated.py` | CLI/config provenance inference |
| JSON output | `src/scieqlint/report/json.py` | scanner/parser/checker behavior |
| Docs | `docs/` | code unless examples are being corrected |

One issue should normally stay in one row.
