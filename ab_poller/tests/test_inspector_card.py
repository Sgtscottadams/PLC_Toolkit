from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QTableWidget

from plc_toolkit.ui.workspace_view import BrowseTab
from plck.models import (
    PlcConnection,
    ReadResult,
    ReadQuality,
    TagNode,
    TagTree,
    TagDataType,
)


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _tree():
    return TagTree(
        plc=PlcConnection(nickname="Test", ip="192.0.2.10"),
        root=[
            TagNode(name="PIT204.PV", data_type=TagDataType.REAL),
            TagNode(name="FT101", data_type=TagDataType.DINT),
        ],
        discovered_at="2026-06-17T00:00:00Z",
    )


def _find_item(tab, tag):
    """Depth-first search for a tree item by full tag path."""
    for i in range(tab.tree.topLevelItemCount()):

        def walk(item):
            if item.data(0, BrowseTab._ROLE_PATH) == tag:
                return item
            for c in range(item.childCount()):
                found = walk(item.child(c))
                if found:
                    return found
            return None

        found = walk(tab.tree.topLevelItem(i))
        if found:
            return found
    return None


def _panel(tab):
    layout = tab.inspector.layout()
    return layout.itemAt(layout.count() - 1).widget()


def test_inspector_includes_recent_reads_table(qapp):
    tab = BrowseTab()
    tab.load_tree(_tree())

    # Select PIT204.PV.
    item = _find_item(tab, "PIT204.PV")
    tab.tree.setCurrentItem(item)
    panel = _panel(tab)

    assert hasattr(panel, "_reads_table")
    tbl = panel._reads_table
    assert isinstance(tbl, QTableWidget)
    assert tbl.columnCount() == 3
    assert tbl.horizontalHeaderItem(0).text() == "Time"
    assert tbl.horizontalHeaderItem(1).text() == "Value"
    assert tbl.horizontalHeaderItem(2).text() == "Quality"


def test_tree_has_value_column_and_defaults_to_placeholder(qapp):
    tab = BrowseTab()
    tab.load_tree(_tree())

    item = _find_item(tab, "PIT204.PV")
    assert item is not None
    # Column 2 is "Value" — starts as "—".
    assert item.text(2) == "—"


def test_tree_value_updates_on_inspector_sample(qapp):
    tab = BrowseTab()
    tab.load_tree(_tree())

    item = _find_item(tab, "PIT204.PV")
    tab.tree.setCurrentItem(item)
    panel = _panel(tab)

    # Simulate an inspector sample arriving at the panel.
    r = ReadResult(
        tag_name="PIT204.PV",
        value=847.2,
        quality=ReadQuality.GOOD,
        elapsed_ms=12.0,
    )
    # Directly invoke the private handler — the worker doesn't run in headless.
    tab._on_inspector_sample(panel, r)

    assert item.text(2) == "847.2"
    assert panel._value_label.text() == "847.2"


def test_inspector_reads_table_populates_on_sample(qapp):
    tab = BrowseTab()
    tab.load_tree(_tree())

    item = _find_item(tab, "PIT204.PV")
    tab.tree.setCurrentItem(item)
    panel = _panel(tab)

    for i in range(3):
        r = ReadResult(
            tag_name="PIT204.PV",
            value=float(i + 1),
            quality=ReadQuality.GOOD,
            elapsed_ms=10.0,
        )
        tab._on_inspector_sample(panel, r)

    tbl = panel._reads_table
    assert tbl.rowCount() == 3
    # Most recent entry is at row 0 (prepended).
    assert tbl.item(0, 1).text() == "3.0"
