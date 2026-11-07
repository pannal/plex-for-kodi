# PM4K (plex-for-kodi) — agent notes

## Environment: use `uv`, not bare pip/pytest

This repo uses **uv** for the virtualenv and dependency management. Do not `pip install`
into the system Python, do not assume a pytest is on PATH, and do not hand-create a venv.

```bash
uv run pytest              # runs the suite with .venv resolved automatically
uv run pytest -q           # quiet
uv run pytest tests/test_x.py::test_y -k pattern
uv add --group dev <pkg>   # add a dep to the dev group in pyproject.toml
uv sync                    # materialise .venv from uv.lock
```

* `pyproject.toml` holds the `[dependency-groups] dev` list **and** the pytest config
  (`[tool.pytest.ini_options]`) — the old top-level `pytest.ini` was removed and its
  contents moved there.
* `uv.lock` is committed. `.venv/` is gitignored.
* Dev deps are only: `pytest`, `requests`, `six`, `iso639-lang`. Everything else the tests
  import is stdlib or in-tree (`lib/`, `tests/kodienv`). Runtime deps (`requests`, `six`)
  come from Kodi addons per `addon.xml`, not from PyPI at runtime.
* `uv run pytest` from a clean checkout must give **717 passed**. If it does not, the
  environment is wrong before the code is.
* Probes in `docs/probes/` are stdlib-only by design — keep them that way. Do not add
  `requests` or any dependency to a probe; they run with plain `python3`.