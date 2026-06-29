"""History tab compare checkbox behavior."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from plc_toolkit.ui.workspace_view import HistoryTab
from plck.db import DatabaseManager
from plck.models import PlcConnection, TagNode, TagDataType, TagTree


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_compare_keeps_at_most_two_checked(qapp, tmp_path):
    db = DatabaseManager(path=str(tmp_path / "hist.db"))
    plc = PlcConnection(nickname="T", ip="10.0.0.1")
    plc_id = db.upsert_plc(plc)
    for i in range(4):
        tree = TagTree(
            plc=plc,
            root=[TagNode(name=f"Tag{i}", data_type=TagDataType.DINT)],
            discovered_at=f"2026-06-24T12:0{i}:00Z",
        )
        db.save_tag_snapshot(plc_id, tree)

    tab = HistoryTab(db)
    tab.set_plc(plc)
    assert tab.table.rowCount() == 4
    assert len(tab._compare_cells) == 4

    def _user_check(tab: HistoryTab, row: int) -> None:
        """Simulate the operator clicking a compare checkbox."""
        tab._compare_cells[row]._box.setChecked(True)

    _user_check(tab, 0)
    _user_check(tab, 1)
    assert tab.compare_btn.isEnabled()
    assert sum(c.is_checked() for c in tab._compare_cells) == 2

    _user_check(tab, 2)
    assert sum(c.is_checked() for c in tab._compare_cells) == 2
    assert tab.compare_btn.isEnabled()
    assert 2 in tab._compare_order
    assert 0 not in tab._compare_order

    _user_check(tab, 3)
    checked_rows = [r for r, c in enumerate(tab._compare_cells) if c.is_checked()]
    assert checked_rows == [2, 3]
    assert tab.compare_btn.isEnabled()
    db.close()
