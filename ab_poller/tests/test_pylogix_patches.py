"""Regression tests for the pylogix resilience shims.

Pins the fix for the field-reported discovery crash on CompactLogix /
ControlLogix units that reject the UDT template service:
``Could not discover tags: 'NoneType' object is not subscriptable``.
"""

from __future__ import annotations

from pylogix.eip import PLC

import plck.pylogix_patches as pp


def _make_plc() -> PLC:
    # pylogix.PLC() does not connect on construction — safe for unit tests.
    return PLC(ip_address="127.0.0.1")


def test_install_is_idempotent():
    pp.install()
    first = PLC._get_udt
    pp.install()
    assert PLC._get_udt is first


def test_template_attribute_none_becomes_empty_bytes(monkeypatch):
    pp.install()
    monkeypatch.setitem(pp._ORIGINALS, "get_template_attribute", lambda self, inst: None)
    plc = _make_plc()
    assert plc._get_template_attribute(123) == b""


def test_template_none_becomes_empty_bytes(monkeypatch):
    pp.install()
    monkeypatch.setitem(pp._ORIGINALS, "get_template", lambda self, inst, n: None)
    plc = _make_plc()
    assert plc._get_template(123, 8) == b""


def test_get_udt_degrades_to_flat_list_on_error(monkeypatch):
    pp.install()

    def _boom(self, tag_list):
        raise RuntimeError("template service rejected (simulated 102/103)")

    monkeypatch.setitem(pp._ORIGINALS, "get_udt", _boom)
    plc = _make_plc()
    flat = ["tag_a", "tag_b"]
    # Must not raise; returns the flat tag list unchanged.
    assert plc._get_udt(flat) == flat


def test_get_udt_passes_through_on_success(monkeypatch):
    pp.install()
    monkeypatch.setitem(
        pp._ORIGINALS, "get_udt", lambda self, tag_list: ["expanded"]
    )
    plc = _make_plc()
    assert plc._get_udt(["x"]) == ["expanded"]
