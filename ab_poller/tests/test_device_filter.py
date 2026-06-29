"""Tests for Logix controller classification (subnet scan filter)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from plck.device_filter import (
    filter_tag_readable_devices,
    is_tag_readable_controller,
    normalize_product_name,
)


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    "product_name, expected",
    [
        ("1756-L83E/B", True),
        ("1769-L24ER-QBFC1B", True),
        ("5069-L306ER", True),
        ("2080-LC50-48QWB", True),
        ("2085-L500E", True),
        ("2711P-T15C22D8P", False),
        ("2715P-T7CD", False),
        ("1783-BMS20CGN", False),
        ("1756-EN2TR", False),
        ("1794-AENT", False),
        ("", False),
        (None, False),
    ],
)
def test_is_tag_readable_controller(product_name, expected):
    assert is_tag_readable_controller(product_name, vendor=1) is expected


@pytest.mark.parametrize(
    "product_name, family",
    [
        ("1769-L33ER", "CompactLogix"),
        ("5069-L306ER", "CompactLogix"),
        ("1756-L83E/B", "ControlLogix"),
        ("2080-LC50-48QWB", "Micro800"),
        ("2085-L500E", "Micro850"),
        ("2711P-T15", ""),
    ],
)
def test_device_family_name(product_name, family):
    from plck.device_filter import device_family_name

    assert device_family_name(product_name) == family


def test_format_device_display():
    from plck.device_filter import format_device_display

    assert format_device_display("1769-L33ER") == "CompactLogix · 1769-L33ER"
    assert format_device_display("1756-L83E/B") == "ControlLogix · 1756-L83E"
    assert format_device_display(None, ip="10.0.0.1") == "10.0.0.1"


def test_non_rockwell_vendor_rejected():
    assert is_tag_readable_controller("1756-L83E", vendor=2) is False


def test_rockwell_vendor_string_accepted():
    assert is_tag_readable_controller(
        "1756-L83E",
        vendor="Rockwell Automation/Allen-Bradley",
    ) is True


@pytest.mark.parametrize(
    "vendor, expected",
    [
        (1, 1),
        ("1", 1),
        ("Rockwell Automation/Allen-Bradley", 1),
        ("Allen-Bradley", 1),
        (None, None),
        ("Siemens", None),
    ],
)
def test_normalize_vendor_id(vendor, expected):
    from plck.device_filter import normalize_vendor_id

    assert normalize_vendor_id(vendor) == expected


def test_filter_with_string_vendor_does_not_raise():
    devices = [
        {
            "ip": "10.254.34.10",
            "vendor": "Rockwell Automation/Allen-Bradley",
            "product_name": "1769-L33ER",
        },
    ]
    filtered = filter_tag_readable_devices(devices)
    assert len(filtered) == 1


def test_normalize_product_name_strips_revision():
    assert normalize_product_name("1756-L83E/B") == "1756-L83E"


def test_filter_tag_readable_devices():
    devices = [
        {"ip": "10.0.0.1", "vendor": 1, "product_name": "1756-L83E"},
        {"ip": "10.0.0.2", "vendor": 1, "product_name": "2711P-T15C22D8P"},
        {"ip": "10.0.0.3", "vendor": 1, "product_name": "1769-L33ER"},
        {"ip": "10.0.0.4", "vendor": 1, "product_name": "1783-BMS20CGN"},
    ]
    filtered = filter_tag_readable_devices(devices)
    assert {d["ip"] for d in filtered} == {"10.0.0.1", "10.0.0.3"}


def test_unsupported_connect_remove_from_list(qapp, tmp_path, monkeypatch):
    from plc_toolkit.ui.connection_view import ConnectionView
    from plck.db import DatabaseManager
    from plck.models import PlcConnection

    db = DatabaseManager(path=str(tmp_path / "unsupported.db"))
    db.upsert_plc(
        PlcConnection(
            nickname="Panel",
            ip="10.0.0.9",
            product_name="2711P-T15C22D8P",
            vendor=1,
        )
    )
    view = ConnectionView(db)
    assert len(db.list_plcs()) == 1

    monkeypatch.setattr(
        view, "_unsupported_device_dialog", lambda _plc: "remove",
    )
    view._connect_row(0)
    assert len(db.list_plcs()) == 0
