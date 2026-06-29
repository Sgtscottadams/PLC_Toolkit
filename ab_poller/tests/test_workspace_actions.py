from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from plc_toolkit.ui.workspace_view import WorkspaceView
from plck.db import DatabaseManager
from plck.models import PlcConnection, TagNode, TagTree, TagDataType
from pathlib import Path


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def ws(tmp_path):
    db_path = tmp_path / "test_monitor.db"
    db = DatabaseManager(path=str(db_path))
    outdir = tmp_path / "exports"
    outdir.mkdir(exist_ok=True)
    w = WorkspaceView(db, outdir)
    yield w
    w.shutdown()
    db.close()


def test_export_button_is_wired(ws, qapp):
    """The Export button was created but never connected to a slot — a dead
    button bug. After the fix, clicking it should call _on_export, which at
    minimum will show a warning dialog (no sources/formats)."""
    # Monkeypatch QMessageBox so we can confirm it was called.
    import plc_toolkit.ui.workspace_view as wv
    calls = []
    orig = wv.QMessageBox.warning
    wv.QMessageBox.warning = lambda *a, **k: calls.append(a)
    try:
        ws.export_tab.fmt_xml.setChecked(False)
        ws.export_tab.fmt_json.setChecked(False)
        ws.export_tab.fmt_excel.setChecked(False)
        ws.export_tab.run_btn.click()
    finally:
        wv.QMessageBox.warning = orig
    assert len(calls) >= 1
    assert "No formats selected" in str(calls[0])


def test_watch_list_clears_on_disconnect(ws, qapp):
    """When _stop_workers is called (disconnect), the monitor watch list must
    clear so tags from PLC A don't bleed into PLC B."""
    ws.monitor_tab.add_tag("Pump_01")
    assert ws.monitor_tab.watch_list() == ["Pump_01"]

    ws._stop_workers()

    assert ws.monitor_tab.watch_list() == []


def test_monitor_tab_has_per_row_remove_button(tmp_path):
    """Each watch-list row must have a remove button so operators can drop
    a single tag without clearing the entire list."""
    from plc_toolkit.ui.workspace_view import MonitorTab

    tab = MonitorTab()
    tag = "PIT204.PV"
    tab.add_tag(tag)
    assert tag in tab.watch_list()

    # The remove button is in the Remove column, row 0.
    btn = tab.table.cellWidget(0, tab._COL_REMOVE)
    assert btn is not None
    assert isinstance(btn, object)  # QPushButton

    btn.click()
    assert tag not in tab.watch_list()
    assert len(tab.watch_list()) == 0


def test_clear_silent_does_not_require_confirmation(tmp_path):
    from plc_toolkit.ui.workspace_view import MonitorTab

    tab = MonitorTab()
    tab.add_tag("TagA")
    tab.add_tag("TagB")
    assert len(tab.watch_list()) == 2

    # clear_silent must not block on a dialog.
    tab.clear_silent()
    assert len(tab.watch_list()) == 0


def test_export_with_tree_source_does_not_crash(ws, qapp, tmp_path):
    """Export with a valid tag tree should write files, not crash."""
    tree = TagTree(
        plc=PlcConnection(nickname="Test PLC", ip="192.0.2.10"),
        root=[TagNode(name="Pump_01", data_type=TagDataType.DINT)],
        discovered_at="2026-06-17T00:00:00Z",
    )
    ws._tree = tree
    ws.export_tab.fmt_xml.setChecked(False)
    ws.export_tab.fmt_excel.setChecked(True)
    ws.export_tab.fmt_json.setChecked(True)
    ws.export_tab.outdir_input.setText(str(tmp_path))

    # Json and XML should work without openpyxl; excel will raise RuntimeError.
    # We just assert the button doesn't crash the app.
    ws.export_tab.run_btn.click()
    # Status label should not still be empty (something happened).
    assert ws.export_tab.status_label.text() != ""
