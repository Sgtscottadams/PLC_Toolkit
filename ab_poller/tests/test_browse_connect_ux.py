"""Browse tab connect UX — default tab and inspector reset."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from plck.db import DatabaseManager
from plck.models import PlcConnection
from plc_toolkit.ui.workspace_view import BrowseTab, WorkspaceView


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_reset_inspector_clears_populated_panel(qapp):
    tab = BrowseTab()
    tab._show_inspector("OldTag.PV", is_leaf=True, is_write=False)
    assert tab.inspector.layout().itemAt(0).widget().objectName() == "inspectorPanel"

    tab.reset_inspector()
    w = tab.inspector.layout().itemAt(0).widget()
    assert w is not None
    assert w.objectName() == "inspectorEmpty"


def test_connect_to_selects_browse_tab(qapp, tmp_path):
    db_path = tmp_path / "plc_data.db"
    w = WorkspaceView(
        DatabaseManager(path=str(db_path)),
        tmp_path / "exports",
    )
    w.tabs.setCurrentWidget(w.monitor_tab)
    w.connect_to(PlcConnection(nickname="T", ip="10.0.0.1"))
    assert w.tabs.currentWidget() is w.browse_tab
