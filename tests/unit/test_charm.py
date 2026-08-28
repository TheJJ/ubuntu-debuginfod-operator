# Copyright 2025 Jonas Jelten <jonas.jelten@canonical.com>
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest
from ops.testing import ActiveStatus, BlockedStatus, Context, Resource, Secret, State

from charm import UbuntuDebuginfodCharm
from config import Config
from ubuntu_debuginfod import UbuntuDebuginfod

# Import the function to be tested
from util import file_ensure_content


@pytest.fixture
def ctx() -> Context:
    """Create a standard context for the charm."""
    return Context(UbuntuDebuginfodCharm)


@patch("os.chown")
def test_install_success(
    mock_os_chown,
    fake_process,  # fixture from pytest-process
    ctx,
    tmp_path,
):
    """
    Test successful installation with valid config.
    """

    # any command can be called
    fake_process.register([fake_process.any()])
    # allow infinite calls
    fake_process.keep_last_process(True)

    # custom env var to signal testing environment basedir
    os.environ["JUJU_CHARM_PREFIX"] = str(tmp_path)

    # run juju install hook
    state = State(leader=True)
    out = ctx.run(ctx.on.install(), state)

    assert isinstance(out.unit_status, ActiveStatus)

    installed_packages = [
        "debuginfod",
        "ubuntu-debuginfod",
    ]
    for pkg in installed_packages:
        assert fake_process.call_count(["apt", "install", "-y", fake_process.any(), pkg]) == 1

    assert fake_process.call_count(["add-apt-repository", "-y",
                                    fake_process.any(), "ppa:ubuntu-debuginfod-devs/ubuntu-debuginfod"]) == 1
    assert fake_process.call_count(["apt", "install", "-y", "postgresql"]) == 1
    assert fake_process.call_count(["systemctl", "enable", "--now", "postgresql.service"]) == 1
    assert fake_process.call_count(["runuser", "-u", "postgres", "--", "createuser", "--login", "mirror"]) == 1
    assert fake_process.call_count(
        ["runuser", "-u", "postgres", "--", "createdb", "--owner", "mirror", "ubuntu-debuginfod"]
    ) == 1
    assert (tmp_path / "srv/debug-mirror/ppas").is_dir()
    assert "/srv/debug-mirror/ppas/" in (tmp_path / "etc/systemd/system/debuginfod.service").read_text()


@patch("os.chown")
def test_install_from_package_resources(mock_os_chown, fake_process, ctx, tmp_path):
    fake_process.register([fake_process.any()])
    fake_process.keep_last_process(True)
    os.environ["JUJU_CHARM_PREFIX"] = str(tmp_path)
    ubuntu_debuginfod_deb = tmp_path / "ubuntu-debuginfod.deb"
    python_debuginfod_deb = tmp_path / "python3-ubuntu-debuginfod.deb"
    ubuntu_debuginfod_deb.touch()
    python_debuginfod_deb.touch()
    state = State(
        leader=True,
        config={"package_source": "resource"},
        resources={
            Resource(name="ubuntu-debuginfod-deb", path=ubuntu_debuginfod_deb),
            Resource(name="python3-ubuntu-debuginfod-deb", path=python_debuginfod_deb),
        },
    )

    out = ctx.run(ctx.on.install(), state)

    assert isinstance(out.unit_status, ActiveStatus)
    assert fake_process.call_count(
        ["add-apt-repository", "-y", "ppa:ubuntu-debuginfod-devs/ubuntu-debuginfod"]
    ) == 0
    assert fake_process.call_count(
        [
            "apt",
            "install",
            "-y",
            "--no-install-recommends",
            str(ubuntu_debuginfod_deb),
            str(python_debuginfod_deb),
        ]
    ) == 1


@patch("shutil.chown")
def test_configure_writes_toml_and_stops_services_in_testmode(
    mock_chown, fake_process, tmp_path
):
    fake_process.register(
        [
            "systemctl",
            "show",
            "multi-user.target",
            "--property=Wants",
            "--value",
        ],
        stdout="",
    )
    fake_process.register(
        [
            "systemctl",
            "disable",
            "--now",
            "ubuntu-debuginfod-launchpad-downloader@1.service",
        ],
        returncode=1,
    )
    fake_process.register([fake_process.any()])
    fake_process.keep_last_process(True)
    config_dir = tmp_path / "home/mirror/.config/ubuntu-debuginfod"
    config_dir.mkdir(parents=True)
    credentials_path = config_dir / "lp.cred"
    credentials_path.write_text("stale credentials")

    UbuntuDebuginfod(tmp_path).configure(
        unit=None,
        config=Config(update_ddeb=True, testmode=True, use_reverse_proxy=False),
    )

    config_toml = (config_dir / "config.toml").read_text()
    assert 'mirror_dir = "/srv/debug-mirror"' in config_toml
    assert config_toml.count("[[ppas]]") == 5
    assert 'user = "ubuntu-esm"' in config_toml
    assert 'name = "realtime-updates"' in config_toml
    assert config_toml.count("private = true") == 5
    assert "database_url" not in config_toml
    assert not credentials_path.exists()

    stopped_services = [
        "ubuntu-debuginfod-launchpad-downloader@1.service",
        "ubuntu-debuginfod-launchpad-cleaner.timer",
        "ubuntu-debuginfod-launchpad-cleaner.service",
        "ubuntu-debuginfod-launchpad-poller.service",
    ]
    for service in stopped_services:
        assert fake_process.call_count(["systemctl", "disable", "--now", service]) == 1

@patch("shutil.chown")
def test_start_success(
    mock_chown,
    fake_process,  # fixture from pytest-process
    ctx,
    tmp_path,
):
    """
    Test successful start.
    """
    secret = Secret({"cred": "x"})  # lp_credentials; required for active status
    state = State(
        leader=True,
        config={"update_ddeb": True, "lp_credentials": secret.id},
        secrets=[secret],
    )

    downloader_units_command = [
        "systemctl",
        "show",
        "multi-user.target",
        "--property=Wants",
        "--value",
    ]
    fake_process.register(downloader_units_command, stdout="")
    fake_process.register(
        downloader_units_command,
        stdout="ubuntu-debuginfod-launchpad-downloader@1.service postgresql.service\n",
    )
    fake_process.register([fake_process.any()])
    fake_process.keep_last_process(True)

    # custom env var to signal testing environment basedir
    os.environ["JUJU_CHARM_PREFIX"] = str(tmp_path)

    # run juju start hook
    out = ctx.run(ctx.on.start(), state)

    assert isinstance(out.unit_status, ActiveStatus)
    assert fake_process.call_count(
        ["systemctl", "enable", "ubuntu-debuginfod-launchpad-cleaner.timer"]
    ) == 1

    started_services = [
        "debuginfod.service",
        "ubuntu-debuginfod-launchpad-downloader@1.service",
        "ubuntu-debuginfod-launchpad-cleaner.service",
        "ubuntu-debuginfod-launchpad-cleaner.timer",
        "ubuntu-debuginfod-launchpad-poller.service",
    ]
    for pkg in started_services:
        assert fake_process.call_count(["systemctl", "restart", fake_process.any(), pkg]) == 1


def test_start_blocked_without_lp_credentials(fake_process, ctx, tmp_path):
    """Start without lp_credentials must not touch services and report blocked."""
    fake_process.register([fake_process.any()])
    fake_process.keep_last_process(True)

    os.environ["JUJU_CHARM_PREFIX"] = str(tmp_path)

    state = State(leader=True, config={"update_ddeb": True})
    out = ctx.run(ctx.on.start(), state)

    assert isinstance(out.unit_status, BlockedStatus)
    assert "lp_credentials" in out.unit_status.message
    assert fake_process.call_count(["systemctl", "restart", fake_process.any()]) == 0


def test_restart_reconciles_downloader_workers(fake_process):
    downloader_units_command = [
        "systemctl",
        "show",
        "multi-user.target",
        "--property=Wants",
        "--value",
    ]
    fake_process.register(
        downloader_units_command,
        stdout=(
            "ubuntu-debuginfod-launchpad-downloader@1.service "
            "ubuntu-debuginfod-launchpad-downloader@2.service "
            "ubuntu-debuginfod-launchpad-downloader@3.service postgresql.service\n"
        ),
    )
    fake_process.register([fake_process.any()])
    fake_process.keep_last_process(True)
    config = Config(
        update_ddeb=False,
        downloader_workers=2,
        testmode=False,
        use_reverse_proxy=False,
    )

    UbuntuDebuginfod(Path("/")).restart(unit=None, config=config)

    assert fake_process.call_count(
        [
            "systemctl",
            "disable",
            "--now",
            "ubuntu-debuginfod-launchpad-downloader@3.service",
        ]
    ) == 1
    for worker in (1, 2):
        service = f"ubuntu-debuginfod-launchpad-downloader@{worker}.service"
        assert fake_process.call_count(["systemctl", "enable", service]) == 1
        assert fake_process.call_count(["systemctl", "restart", service]) == 1


@patch("shutil.chown")
def test_upgrade_configures_before_start(mock_chown, fake_process, ctx, tmp_path):
    fake_process.register([fake_process.any()])
    fake_process.keep_last_process(True)
    os.environ["JUJU_CHARM_PREFIX"] = str(tmp_path)

    out = ctx.run(ctx.on.upgrade_charm(), State(leader=True, config={"testmode": True}))

    assert isinstance(out.unit_status, ActiveStatus)
    config_path = tmp_path / "home/mirror/.config/ubuntu-debuginfod/config.toml"
    assert config_path.is_file()
    assert "[[ppas]]" in config_path.read_text()


@patch("shutil.chown")
def test_secret_changed_refreshes_launchpad_credentials(mock_chown, fake_process, ctx, tmp_path):
    fake_process.register([fake_process.any()])
    fake_process.keep_last_process(True)
    os.environ["JUJU_CHARM_PREFIX"] = str(tmp_path)
    secret = Secret({"cred": "old"}, latest_content={"cred": "new"})
    state = State(
        leader=True,
        config={"testmode": True, "lp_credentials": secret.id},
        secrets=[secret],
    )

    ctx.run(ctx.on.secret_changed(secret), state)

    credentials_path = tmp_path / "home/mirror/.config/ubuntu-debuginfod/lp.cred"
    assert credentials_path.read_text() == "new"
    assert stat.S_IMODE(credentials_path.stat().st_mode) == 0o600




def test_stop_success(
    fake_process,  # fixture from pytest-process
    ctx,
    tmp_path,
):
    """
    Test successful stop.
    """

    # any command can be called
    fake_process.register([fake_process.any()])
    # allow infinite calls
    fake_process.keep_last_process(True)

    # custom env var to signal testing environment basedir
    os.environ["JUJU_CHARM_PREFIX"] = str(tmp_path)

    # run juju install hook
    state = State(leader=True, config = {"update_ddeb": True})
    out = ctx.run(ctx.on.stop(), state)

    assert isinstance(out.unit_status, BlockedStatus)

    stopped_services = [
        "debuginfod.service",
        "ubuntu-debuginfod-launchpad-downloader@1.service",
        "ubuntu-debuginfod-launchpad-cleaner.timer",
        "ubuntu-debuginfod-launchpad-cleaner.service",
        "ubuntu-debuginfod-launchpad-poller.service",
    ]
    for pkg in stopped_services:
        assert fake_process.call_count(["systemctl", "disable", "--now", fake_process.any(), pkg]) == 1


def test_create_new_file_with_content(tmp_path: Path):
    """Tests creating a new file with the specified content."""
    file = tmp_path / "test.file"
    content = "Hai!"

    assert not file.exists()
    file_ensure_content(file, content)

    assert file.is_file()
    assert file.read_text() == content

def test_create_directory_and_file(tmp_path: Path):
    """Tests creating parent directories when mkdir=True."""
    file = tmp_path / "new_dir" / "test.file"
    content = "with directory"

    assert not file.parent.exists()
    file_ensure_content(file, content, mkdir=True)

    assert file.is_file()
    assert file.read_text() == content

def test_overwrite_existing_file_without_matcher(tmp_path: Path):
    """Tests overwriting a file when content differs and no matcher is used."""
    file = tmp_path / "test.file"
    file.write_text("Old content.")
    new_content = "New content!"

    file_ensure_content(file, new_content, append_missing=False)

    assert file.read_text() == new_content

def test_do_nothing_if_content_unchanged(tmp_path: Path):
    """Tests that the file is untouched if content already matches."""
    file = tmp_path / "test.file"
    content = "Content is correct."
    file.write_text(content)
    prev_mtime = file.stat().st_mtime

    file_ensure_content(file, content)

    assert file.read_text() == content
    assert prev_mtime == file.stat().st_mtime


def test_ensure_file_mode(tmp_path: Path):
    file = tmp_path / "credentials"
    file.write_text("secret")
    file.chmod(0o644)

    assert file_ensure_content(file, "secret", mode=0o600)

    assert stat.S_IMODE(file.stat().st_mode) == 0o600


def test_replace_content_with_matcher(tmp_path: Path):
    """Tests replacing a line that matches the regex."""
    file = tmp_path / "config.conf"
    initial_content = "user=chef\nlevel=2\n"
    file.write_text(initial_content)

    file_ensure_content(
        file,
        content="user=guest",  # used if matcher fails
        matcher=r"(?m)^user=.*$",
        replace="user=guest",
    )

    assert file.read_text() == "user=guest\nlevel=2\n"

def test_append_if_matcher_fails_and_append_is_true(tmp_path: Path):
    """Tests appending content if matcher doesn't find a match (default)."""
    file = tmp_path / "settings.file"
    initial_content = "mode=auto\n"
    file.write_text(initial_content)

    file_ensure_content(
        file,
        content="feature_enabled=true\n",
        matcher=r"^feature_enabled=.*$",
        replace="feature_enabled=true",
    )

    expected_content = "mode=auto\nfeature_enabled=true\n"
    assert file.read_text() == expected_content

def test_overwrite_if_matcher_fails_and_append_is_false(tmp_path: Path):
    """Tests overwriting the file if matcher fails and append_missing is False."""
    file = tmp_path / "settings.file"
    file.write_text("old_setting=old_value")

    new_content = "feature_enabled=true"

    file_ensure_content(
        file,
        content=new_content,
        matcher=r"^feature_enabled=.*$",
        replace="feature_enabled=true",
        append_missing=False,
    )

    assert file.read_text() == new_content

def test_matcher_without_replace_raises_error(tmp_path: Path):
    """Tests that matcher requires replace."""
    file = tmp_path / "test.file"
    file.write_text("some data")

    with pytest.raises(ValueError):
        file_ensure_content(file, "new data", matcher="some")

@patch('shutil.chown')
@patch('charmlibs.pathops.LocalPath.owner', return_value='root')
def test_chown_is_called_when_owner_differs(mock_owner, mock_chown, tmp_path):
    """Tests that shutil.chown is called if the file owner is different."""
    file = tmp_path / "test.file"
    file.touch()

    file_ensure_content(file, "content", owner="new_owner")

    mock_chown.assert_called_once_with(file, user="new_owner", group=None)
