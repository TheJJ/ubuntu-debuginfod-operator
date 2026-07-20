# Agent Guidelines for `ubuntu-debuginfod-operator`

This is a [Juju charm](https://juju.is/charms-architecture) (built with the [`ops`](https://documentation.ubuntu.com/ops) framework) that deploys `ubuntu-debuginfod` and `debuginfod` to serve Ubuntu package debug symbols. See [README.md](README.md) and [doc/README.md](doc/README.md) for functional/architecture details.

## Tooling

- `uv` for dependency management/venvs
- `ruff` for linting/formatting
- `ty` for type checking.

```console
# sync the environment (creates .venv)
uv sync --all-extras --dev

# lint
uv run ruff check

# type check
uv run ty check src

# unit tests
uv run pytest --log-cli-level=DEBUG --tb native tests/unit

# integration tests (needs a Juju controller/model)
uv run pytest --log-cli-level=DEBUG --tb native tests/integration

# build the charm (needs the charmcraft snap)
charmcraft pack
```

Always run `uv run ruff check` and `uv run pytest tests/unit` before considering a change complete (CI in `.github/workflows/test.yaml` runs the same two steps).

## Code layout

- [src/charm.py](src/charm.py): the `ops.CharmBase` entrypoint; wires up Juju hooks/events, ingress, and orchestrates the two services below. **This class is instantiated fresh for every hook invocation** — do not rely on in-memory state surviving between hooks; use `ops.StoredState` or re-derive state from disk/config instead.
- [src/config.py](src/config.py): `pydantic` model mirroring the `config.options` in [charmcraft.yaml](charmcraft.yaml). Keep both in sync when adding/removing config keys.
- [src/ubuntu_debuginfod.py](src/ubuntu_debuginfod.py) / [src/debuginfod.py](src/debuginfod.py): service wrappers (install/configure/restart/stop/is_running) for the two systemd services the charm manages.
- [src/util.py](src/util.py): small helpers (`run_check`/`run_ret`/`run_out` for subprocess, `file_copy`/`file_link`/`file_remove`/`file_ensure_content` for idempotent file management). Hook logic should go through these rather than calling `subprocess`/file APIs directly, so tests can use `pytest-subprocess`'s `fake_process` fixture.
- [etc/](etc/): systemd unit, default env file, and nginx site config shipped verbatim onto the deployed machine.

## Conventions

- All file/directory mutation on the deployed unit goes through `self._root` (a `pathops.LocalPath('/')`, or a `Path` under `$JUJU_CHARM_PREFIX` in tests) — never hardcode absolute paths when writing charm logic, so tests can redirect I/O into a tmp dir.
- `file_ensure_content`'s `matcher`/`replace` args use `re.search` with `re.MULTILINE`; write patterns assuming they may match anywhere in a multi-line file, not just at the start.
- Unit tests use `ops.testing.Context`/`State` plus the `fake_process` fixture (`pytest-subprocess`) to intercept shell calls — see [tests/unit/test_charm.py](tests/unit/test_charm.py) for the pattern.
