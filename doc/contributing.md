# Contributing

To make contributions to this charm, you'll need a working [development setup](https://juju.is/docs/sdk/dev-setup).

You can create an environment for development with `uv`:

``` console
uv sync --all-extras --dev
# this creates .venv
```

## Testing

This project uses `pytest` testing.
that can be used for linting and formatting code when you're preparing contributions to the charm:

``` console
# run unit tests
uv run pytest --log-cli-level=DEBUG --tb native tests/unit
# run integrationt tests
uv run pytest --log-cli-level=DEBUG --tb native tests/integration
```

To test a prebuilt upstream snapshot instead of the production PPA, provide both binary packages from the same source build:

``` console
uv run pytest tests/integration \
	--ubuntu-debuginfod-deb=/path/to/ubuntu-debuginfod_VERSION_all.deb \
	--python3-ubuntu-debuginfod-deb=/path/to/python3-ubuntu-debuginfod_VERSION_all.deb
```

## Build the charm

You need the `charmcraft` snap.

To build the charm file in this git repository:

``` console
charmcraft pack
```

The same package resources can be used without pytest for a manual deployment:

``` console
juju deploy ./ubuntu-debuginfod_*.charm ubuntu-debuginfod \
	--config package_source=resource \
	--resource ubuntu-debuginfod-deb=/path/to/ubuntu-debuginfod_VERSION_all.deb \
	--resource python3-ubuntu-debuginfod-deb=/path/to/python3-ubuntu-debuginfod_VERSION_all.deb
```

To replace the snapshot on an existing local deployment, refresh the charm and both resources together:

``` console
juju refresh ubuntu-debuginfod \
	--path ./ubuntu-debuginfod_*.charm \
	--config package_source=resource \
	--resource ubuntu-debuginfod-deb=/path/to/ubuntu-debuginfod_VERSION_all.deb \
	--resource python3-ubuntu-debuginfod-deb=/path/to/python3-ubuntu-debuginfod_VERSION_all.deb \
	--force
```

With the default `package_source=ppa`, neither resource is fetched and the charm installs the production PPA package.

## Style

We use `ruff` for style checking, `ty` for type checks.

``` console
# to run type checks
uv run ty check
# code style linting
uv run ruff check
```
