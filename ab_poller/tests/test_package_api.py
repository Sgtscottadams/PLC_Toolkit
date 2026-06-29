from __future__ import annotations

import plck


def test_plck_exposes_discovery_submodule():
    # The worker calls `plck.discovery.discover_tags(client)`, and the package
    # docstring advertises `plck.discovery.discover_tags` as public API. The
    # submodule must be importable as an attribute of the package.
    assert hasattr(plck, "discovery")
    assert callable(plck.discovery.discover_tags)
