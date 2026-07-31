#!/usr/bin/env python3
# Copyright 2025 Jonas Jelten <jonas.jelten@canonical.com>
# See LICENSE file for licensing details.

import json
import logging
from pathlib import Path

import jubilant
import requests
import yaml

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())

logger = logging.getLogger(__name__)



def _address(juju_: jubilant.Juju, app_name: str):
    """Get the IP address of the application."""
    return juju_.status().apps[app_name].units[f"{app_name}/0"].public_address


def test_deploy_app(juju: jubilant.Juju, app: str):
    """
    Test if deployment itself works.
    The "app" parameter pulls in the deployment fixture.
    """
    assert app


def test_services_running(
    juju: jubilant.Juju,
    app: str,
    lp_credentials_file: Path | None,
):
    services_raw = juju.ssh(f"{app}/0", "systemctl list-units --type service --full --all --output json")
    services_list = json.loads(services_raw)
    services = {svc["unit"]: svc for svc in services_list}

    assert services["debuginfod.service"]["active"] == "active"
    assert services["postgresql.service"]["active"] == "active"
    for worker in (1, 2):
        service = f"ubuntu-debuginfod-launchpad-downloader@{worker}.service"
        if lp_credentials_file is None:
            assert service not in services or services[service]["active"] != "active"
        else:
            assert services[service]["active"] == "active"


def test_backend_configuration(juju: jubilant.Juju, app: str):
    config = juju.ssh(f"{app}/0", "sudo cat /home/mirror/.config/ubuntu-debuginfod/config.toml")
    assert 'mirror_dir = "/srv/debug-mirror"' in config
    assert config.count("[[ppas]]") == 5
    assert "database_url" not in config

    assert juju.ssh(f"{app}/0", "test -d /srv/debug-mirror/ppas && echo present").strip() == "present"
    assert (
        juju.ssh(
            f"{app}/0",
            "sudo -u postgres psql -tAc \"select rolcanlogin from pg_roles where rolname = 'mirror'\" postgres",
        ).strip()
        == "t"
    )
    assert (
        juju.ssh(
            f"{app}/0",
            "sudo -u mirror psql -tAc \"select to_regclass('public.download_job')\" ubuntu-debuginfod",
        ).strip()
        == "download_job"
    )


def test_application_is_up(juju: jubilant.Juju, app: str):
    response = requests.get(f"http://{_address(juju, app)}:8002", timeout=30)
    assert response.status_code == 200
    # TODO testmode to provide selected debug data
    buildid = "d11ba2e3311344ed7ce2745a3a7942c76a54fba8"
    response = requests.get(
        f"http://{_address(juju, app)}:8002/buildid/{buildid}/debuginfo",
        timeout=30,
    )
    # assert response.status_code == 200
