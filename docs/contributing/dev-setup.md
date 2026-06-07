# Development setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,docs]'
pytest
ruff format --check .
ruff check .
pyright
```

Using `uv` is encouraged after the repository has a lockfile.

```bash
uv sync --group dev --extra docs
uv run pytest
```
