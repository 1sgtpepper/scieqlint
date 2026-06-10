# Architecture map for contributors

| Goal | Start here | Avoid touching |
|---|---|---|
| CLI command behavior | `src/scieqlint/cli.py` | scanner/parser/checker internals |
| Config defaults | `src/scieqlint/config/` | reporters |
| Source locations | `src/scieqlint/io/source.py` | algebra |
| Markdown extraction | `src/scieqlint/scan/markdown.py`, `src/scieqlint/scan/markdown_semantics.py` | parser/checkers |
| LaTeX extraction | `src/scieqlint/scan/latex.py`, `src/scieqlint/scan/latex_semantics.py`, `src/scieqlint/scan/latex_support.py`, `src/scieqlint/scan/latex_symbols.py` | parser/checkers |
| Grammar | `src/scieqlint/parse/grammar.lark` | reporters |
| Algebra | `src/scieqlint/check/algebra.py`, `src/scieqlint/check/algebra_poly.py` | scanner |
| Dimensions | `src/scieqlint/check/dimensions.py`, `src/scieqlint/check/dimensions_parser.py` | scanner |
| References | `src/scieqlint/check/references.py` | algebra |
| JSON output | `src/scieqlint/report/json.py` | scanner/parser/checker behavior |
| Docs | `docs/` | code unless examples are being corrected |

One issue should normally stay in one row.
