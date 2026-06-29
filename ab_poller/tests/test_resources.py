"""Tests for bundled asset resolution."""

from __future__ import annotations


def test_asset_path_finds_packaged_logo():
    from plc_toolkit.resources import asset_path

    path = asset_path("clr-logo.png")
    assert path is not None
    assert path.name == "clr-logo.png"
    assert path.is_file()
