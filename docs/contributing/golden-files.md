# Golden files

Golden files lock user-visible output. They must be stable across operating systems.

v0.1.0 golden outputs live under:

```text
tests/golden/text/*.txt
tests/golden/json/*.json
```

Later releases add:

```text
tests/golden/github/*.txt
tests/golden/sarif/*.json
```

When golden output changes, the PR must explain why and update docs if users are affected.
