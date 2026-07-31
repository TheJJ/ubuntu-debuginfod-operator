"""Charm configuration options."""

from __future__ import annotations

from typing import Literal

import ops
import pydantic


class Config(pydantic.BaseModel):
    """Config fields as defined in charmcraft.yaml, with values from juju."""

    # ops.model.Secret is not pydantic-compatible, so we can't actually nest it.
    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    # activate ddeb fetching
    update_ddeb: bool = pydantic.Field()

    # parallel downloader processes on this unit
    downloader_workers: int = pydantic.Field(default=1, ge=1)

    # package installation source
    package_source: Literal["ppa", "resource"] = pydantic.Field(default="ppa")

    # run in testmode
    testmode: bool = pydantic.Field()

    # use nginx reverse proxy
    use_reverse_proxy: bool = pydantic.Field()

    # launchpad secret
    lp_credentials: ops.model.Secret | None = pydantic.Field(default=None)
