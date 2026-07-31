"""Integration test configuration."""

import subprocess
from pathlib import Path

import jubilant
import pytest
import yaml

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())


def _all_active_and_idle(status: jubilant.Status) -> bool:
    return jubilant.all_active(status) and jubilant.all_agents_idle(status)


def pytest_addoption(parser):
    parser.addoption(
        "--charm-file", help="instead of charmcraft pack, use this .charm file"
    )
    parser.addoption(
        "--ubuntu-debuginfod-deb",
        type=Path,
        help="install this prebuilt ubuntu-debuginfod binary package instead of using the PPA",
    )
    parser.addoption(
        "--python3-ubuntu-debuginfod-deb",
        type=Path,
        help="install this prebuilt python3-ubuntu-debuginfod binary package instead of using the PPA",
    )
    parser.addoption(
        "--lp-credentials-file",
        type=Path,
        help="Launchpad credentials file for exercising live downloader workers",
    )


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest):
    """Create a temporary juju model for testing."""
    with jubilant.temp_model() as juju:
        yield juju

        if request.session.testsfailed:
            log = juju.debug_log(limit=2000)
            print("tests failed, here's juju debug-log.")
            print(log, end="")


@pytest.fixture(scope="session")
def charm(request: pytest.FixtureRequest) -> Path:
    """Build the charm for integration testing."""
    charm_file = request.config.getoption("--charm-file")
    if charm_file:
        return Path(charm_file)

    # charmcraft pack apparently can't tell the output filename.
    subprocess.check_call(["charmcraft", "pack", "--verbose"])
    # TODO: charmcraft should provide a way to set the output name...
    return max(Path(".").glob("*.charm"), key=lambda path: path.stat().st_mtime)


@pytest.fixture(scope="session")
def upstream_resources(request: pytest.FixtureRequest) -> dict[str, str] | None:
    """Return optional prebuilt upstream packages as Juju resources."""
    packages = {
        "ubuntu-debuginfod-deb": request.config.getoption("--ubuntu-debuginfod-deb"),
        "python3-ubuntu-debuginfod-deb": request.config.getoption(
            "--python3-ubuntu-debuginfod-deb"
        ),
    }
    provided = {name: path for name, path in packages.items() if path is not None}
    if not provided:
        return None
    if len(provided) != len(packages):
        raise pytest.UsageError("both upstream binary package options must be provided together")
    missing = [path for path in provided.values() if not path.is_file()]
    if missing:
        raise pytest.UsageError(f"upstream binary package does not exist: {missing}")
    return {name: str(path.resolve()) for name, path in provided.items()}


@pytest.fixture(scope="session")
def lp_credentials_file(request: pytest.FixtureRequest) -> Path | None:
    """Return the optional Launchpad credentials file."""
    credentials_file = request.config.getoption("--lp-credentials-file")
    if credentials_file is None:
        return None
    if not credentials_file.is_file():
        raise pytest.UsageError(f"Launchpad credentials file does not exist: {credentials_file}")
    return credentials_file


@pytest.fixture(scope="module")
def app(
    juju: jubilant.Juju,
    charm: Path,
    upstream_resources: dict[str, str] | None,
    lp_credentials_file: Path | None,
):
    """Deploy ubuntu-debuginfod charm."""

    app_name = METADATA["name"]

    # juju expects leading ./ or / for charm files...
    charm_path = str(charm) if charm.is_absolute() else f"./{charm}"

    config = {
        "testmode": True,
        "downloader_workers": 2,
        "package_source": "resource" if upstream_resources else "ppa",
    }

    if app_name in juju.status().apps:
        juju.refresh(
            app_name,
            path=charm_path,
            config=config,
            resources=upstream_resources,
            force=True,
        )

    else:
        juju.deploy(
            charm_path,
            app=app_name,
            config=config,
            resources=upstream_resources,
        )

    juju.wait(_all_active_and_idle, error=jubilant.any_error, timeout=900.0)

    if lp_credentials_file is not None:
        secret = juju.add_secret(
            "debuginfod-launchpad",
            {"cred": lp_credentials_file.read_text()},
        )
        juju.grant_secret(secret, app_name)
        juju.config(
            app_name,
            {
                "lp_credentials": str(secret),
                "testmode": False,
            },
        )
        juju.wait(_all_active_and_idle, error=jubilant.any_error, timeout=900.0)

    yield app_name
