"""Connection Manager Last scan column."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from plck.db import DatabaseManager
from plck.models import PlcConnection, TagNode, TagDataType, TagTree
from plc_toolkit.ui.connection_view import ConnectionView, _format_last_scan


def test_format_last_scan_never():
    assert _format_last_scan(None) == "Never"
    assert _format_last_scan("") == "Never"


def test_format_last_scan_relative():
    recent = datetime.now(timezone.utc) - timedelta(hours=2, minutes=5)
    iso = recent.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    assert _format_last_scan(iso) == "2h ago"


def test_list_plcs_includes_last_scan(tmp_path):
    db = DatabaseManager(path=str(tmp_path / "scan.db"))
    plc = PlcConnection(nickname="Test", ip="10.0.0.1")
    plc_id = db.upsert_plc(plc)
    tree = TagTree(
        plc=plc,
        root=[TagNode(name="Tag1", data_type=TagDataType.DINT)],
        discovered_at="2026-06-24T12:00:00Z",
    )
    db.save_tag_snapshot(plc_id, tree)
    listed = db.list_plcs()
    assert len(listed) == 1
    assert listed[0].last_scan == "2026-06-24T12:00:00Z"


def test_connection_view_shows_last_scan(tmp_path):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    db = DatabaseManager(path=str(tmp_path / "ui_scan.db"))
    plc = PlcConnection(nickname="Skid A", ip="172.17.117.5")
    plc_id = db.upsert_plc(plc)
    tree = TagTree(
        plc=plc,
        root=[TagNode(name="Tag1", data_type=TagDataType.DINT)],
        discovered_at="2026-06-24T08:30:00Z",
    )
    db.save_tag_snapshot(plc_id, tree)

    view = ConnectionView(db)
    assert view.table.item(0, 6).text() != ""
    assert view.table.item(0, 6).text() != "Never"
    db.close()


def test_device_id_column_and_editable_nickname(tmp_path):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    db = DatabaseManager(path=str(tmp_path / "device_id.db"))
    plc = PlcConnection(
        nickname="",
        device_id="1756-L83E",
        ip="10.0.0.50",
        product_name="1756-L83E",
    )
    db.upsert_plc(plc)

    view = ConnectionView(db)
    assert view.table.item(0, 0).text() == ""
    assert view.table.item(0, 1).text() == "ControlLogix · 1756-L83E"

    view.table.item(0, 0).setText("Compressor Skid A")
    view._on_nickname_edited(view.table.item(0, 0))
    listed = db.list_plcs()
    assert listed[0].nickname == "Compressor Skid A"
    assert listed[0].device_id == "1756-L83E"
    db.close()


def test_device_label_prefers_product_over_ip_stored_as_device_id():
    plc = PlcConnection(
        nickname="",
        ip="10.254.34.50",
        device_id="10.254.34.50",
        product_name="1769-L33ER",
    )
    assert plc.device_label() == "1769-L33ER"


def test_upsert_stores_catalog_not_ip_when_product_known(tmp_path):
    db = DatabaseManager(path=str(tmp_path / "catalog.db"))
    plc = PlcConnection(
        nickname="",
        ip="10.254.34.50",
        product_name="1769-L33ER",
    )
    db.upsert_plc(plc)
    listed = db.list_plcs()
    assert listed[0].device_id == "1769-L33ER"
    assert listed[0].device_id != listed[0].ip


def test_subnet_batch_add_sets_catalog_and_revision(tmp_path):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    db = DatabaseManager(path=str(tmp_path / "batch.db"))
    view = ConnectionView(db)
    devices = [
        {
            "ip": "10.254.34.51",
            "product_name": "5069-L306ER",
            "revision": "35.11",
            "vendor": 1,
        },
    ]
    view._on_devices_selected(devices)
    listed = db.list_plcs()
    assert listed[0].device_label() == "5069-L306ER"
    assert listed[0].revision == "35.11"
    assert view.table.item(0, 1).text() == "CompactLogix · 5069-L306ER"
    assert view.table.item(0, 5).text() == "35.11"
    db.close()


def test_device_id_migration_backfill(tmp_path):
    db = DatabaseManager(path=str(tmp_path / "migrate.db"))
    db.conn.execute(
        """INSERT INTO plcs (ip, slot, name, product_name)
           VALUES ('10.0.0.1', 0, 'Old Nick', '1769-L24ER')"""
    )
    db.conn.commit()
    db._migrate()
    row = db.conn.execute(
        "SELECT device_id FROM plcs WHERE ip = '10.0.0.1'"
    ).fetchone()
    assert row["device_id"] == "1769-L24ER"
    db.close()
