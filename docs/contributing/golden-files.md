# Golden files

Golden files lock user-visible output. They must be stable across operating systems.

Current golden outputs live under:

```text
tests/golden/text/
tests/golden/json/
tests/golden/github/
tests/golden/sarif/
tests/golden/graph/
```

Graph goldens are JSON too. When expected output changes, explain the behavior change
and update affected public examples or docs.
