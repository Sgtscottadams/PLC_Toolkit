"""Tests for tag display helpers and scan value persistence."""

from __future__ import annotations

from plck.models import TagNode, TagDataType, PlcConnection, TagTree
from plck.tag_display import format_type_label


def test_udt_type_shows_member_count():
    node = TagNode(
        name="PIT204",
        data_type=TagDataType.UDT,
        members=[
            TagNode(name="PIT204.PV", data_type=TagDataType.REAL),
            TagNode(name="PIT204.Sts", data_type=TagDataType.DINT),
        ],
    )
    assert format_type_label(node) == "UDT (2)"


def test_leaf_type_unchanged():
    node = TagNode(name="FT101", data_type=TagDataType.REAL)
    assert format_type_label(node) == "REAL"


def test_save_and_load_scan_values(tmp_path):
    from plck.db import DatabaseManager

    db = DatabaseManager(path=str(tmp_path / "v.db"))
    plc_id = db.upsert_plc(PlcConnection(nickname="T", ip="192.0.2.5"))
    tree = TagTree(
        plc=PlcConnection(nickname="T", ip="192.0.2.5"),
        root=[TagNode(name="FT101", data_type=TagDataType.REAL)],
        discovered_at="2026-06-24T12:00:00Z",
    )
    scan_id = db.save_tag_snapshot(plc_id, tree)
    db.save_scan_values(scan_id, {"FT101": 42.5, "FT102": True})
    loaded = db.load_scan_values(scan_id)
    assert loaded["FT101"] == 42.5
    assert loaded["FT102"] is True


def test_update_scan_notes(tmp_path):
    from plck.db import DatabaseManager

    db = DatabaseManager(path=str(tmp_path / "n.db"))
    plc_id = db.upsert_plc(PlcConnection(nickname="T", ip="192.0.2.6"))
    tree = TagTree(
        plc=PlcConnection(nickname="T", ip="192.0.2.6"),
        root=[TagNode(name="A", data_type=TagDataType.BOOL)],
        discovered_at="2026-06-24T12:00:00Z",
    )
    scan_id = db.save_tag_snapshot(plc_id, tree, notes="")
    db.update_scan_notes(scan_id, "Pre-maintenance baseline")
    scans = db.list_scans(plc_id)
    assert scans[0]["notes"] == "Pre-maintenance baseline"
