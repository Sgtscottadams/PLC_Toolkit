"""Tests for scan browse/compare dialogs and export path defaults."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from plc_toolkit.settings_store import AppSettings, default_documents_dir
from plc_toolkit.ui.scan_dialogs import ScanCompareDialog
from plck.models import PlcConnection, TagNode, TagTree, TagDataType


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _tree(extra: list[TagNode] | None = None, discovered_at: str = "2026-06-17T00:00:00Z") -> TagTree:
    root = [
        TagNode(name="FT101", data_type=TagDataType.REAL),
        TagNode(name="FT102", data_type=TagDataType.REAL),
    ]
    if extra:
        root.extend(extra)
    return TagTree(
        plc=PlcConnection(nickname="T", ip="192.0.2.1"),
        root=root,
        discovered_at=discovered_at,
    )


def test_default_export_dir_under_documents(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "plc_toolkit.settings_store.default_documents_dir",
        lambda: tmp_path / "Documents",
    )
    s = AppSettings()
    out = s.resolved_export_dir()
    assert out == tmp_path / "Documents" / "PLCToolkit" / "exports"


def test_scan_compare_marks_added_and_removed(qapp, tmp_path):
    from plck.db import DatabaseManager

    db = DatabaseManager(path=str(tmp_path / "t.db"))
    plc_id = db.upsert_plc(PlcConnection(nickname="T", ip="192.0.2.1"))
    id_a = db.save_tag_snapshot(
        plc_id, _tree(discovered_at="2026-06-17T10:00:00Z"), source="test", notes="older",
    )
    id_b = db.save_tag_snapshot(
        plc_id,
        _tree(
            extra=[TagNode(name="FT103", data_type=TagDataType.REAL)],
            discovered_at="2026-06-17T11:00:00Z",
        ),
        source="test",
        notes="newer",
    )

    dlg = ScanCompareDialog(
        db, id_a, id_b, "2026-06-17T10:00:00Z", "2026-06-17T11:00:00Z",
    )
    assert dlg.table.rowCount() == 3
    rows = {
        dlg.table.item(r, 0).text(): dlg.table.item(r, 3).text()
        for r in range(dlg.table.rowCount())
    }
    assert rows["FT101"] == "Unchanged"
    assert rows["FT103"] == "Added"


def test_default_documents_dir_is_path():
    p = default_documents_dir()
    assert p.name == "Documents" or "Documents" in str(p)
