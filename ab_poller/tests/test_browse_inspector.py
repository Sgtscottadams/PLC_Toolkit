from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from plc_toolkit.ui.workspace_view import BrowseTab
from plck.models import PlcConnection, TagNode, TagTree, TagDataType


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _tree():
    # PIT204 is a UDT parent (has members) — NOT directly readable.
    # PIT204.PV is an atomic leaf — readable.
    pit = TagNode(
        name="PIT204",
        data_type=TagDataType.UDT,
        udt_name="P_AIn",
        members=[
            TagNode(name="PIT204.PV", data_type=TagDataType.REAL),
            TagNode(name="PIT204.Sts", data_type=TagDataType.DINT),
        ],
    )
    flow = TagNode(name="FT101", data_type=TagDataType.REAL)
    facility = TagNode(name="Facility101", data_type=TagDataType.REAL)
    cmd = TagNode(name="Pump01.Cmd", data_type=TagDataType.BOOL, is_write_tag=True)
    return TagTree(
        plc=PlcConnection(nickname="Test", ip="192.0.2.10"),
        root=[pit, flow, facility, cmd],
        discovered_at="2026-06-17T00:00:00Z",
    )


def _panel(tab):
    # The inspector panel is the last widget added to the inspector layout.
    layout = tab.inspector.layout()
    return layout.itemAt(layout.count() - 1).widget()


def _select_path(tab, full_path):
    """Select the tree item whose stored path == full_path (depth-first)."""
    def walk(item):
        if item.data(0, BrowseTab._ROLE_PATH) == full_path:
            return item
        for i in range(item.childCount()):
            found = walk(item.child(i))
            if found:
                return found
        return None

    for i in range(tab.tree.topLevelItemCount()):
        found = walk(tab.tree.topLevelItem(i))
        if found:
            tab.tree.setCurrentItem(found)
            return found
    raise AssertionError(f"path not found in tree: {full_path}")


def test_inspector_buttons_are_wired(qapp):
    tab = BrowseTab()
    tab.load_tree(_tree())
    _select_path(tab, "PIT204.PV")
    panel = _panel(tab)

    # Prove the buttons are wired by observing their side effects, not by
    # inspecting Qt internals. A dead button (the original bug) produces no
    # effect on click.
    QApplication.clipboard().setText("__sentinel__")
    panel._copy_btn.click()
    assert QApplication.clipboard().text() == "PIT204.PV"

    received = []
    tab.navigate_to_monitor_requested.connect(received.append)
    panel._add_btn.click()
    assert received == ["PIT204.PV"]

    # Chart history opens a live chart dialog (non-blocking in tests).
    import plc_toolkit.ui.workspace_view as wv
    opened = []
    orig_exec = wv.TagChartDialog.exec

    def _fake_exec(self):
        opened.append(self._tag)
        return 0

    wv.TagChartDialog.exec = _fake_exec
    try:
        panel._hist_btn.click()
    finally:
        wv.TagChartDialog.exec = orig_exec
    assert opened == ["PIT204.PV"]


def test_copy_tag_path_writes_full_path_to_clipboard(qapp):
    tab = BrowseTab()
    tab.load_tree(_tree())
    _select_path(tab, "PIT204.PV")
    panel = _panel(tab)

    panel._copy_btn.click()
    assert QApplication.clipboard().text() == "PIT204.PV"


def test_add_to_monitor_emits_full_path(qapp):
    tab = BrowseTab()
    tab.load_tree(_tree())
    _select_path(tab, "PIT204.PV")
    panel = _panel(tab)

    received = []
    tab.navigate_to_monitor_requested.connect(received.append)
    panel._add_btn.click()
    assert received == ["PIT204.PV"]


def test_udt_root_is_not_auto_read_and_cannot_be_monitored(qapp):
    # Selecting the UDT parent (PIT204) must NOT start an inspector poll
    # (aggregate read on the UDT root is what Logix rejects with a privilege
    # violation) and must disable "+ Add to Monitor".
    tab = BrowseTab()
    tab.set_plc(PlcConnection(nickname="Test", ip="192.0.2.10"))
    tab.load_tree(_tree())
    _select_path(tab, "PIT204")
    panel = _panel(tab)

    assert panel._is_leaf is False
    assert tab._inspector_worker is None
    assert panel._add_btn.isEnabled() is False


def test_write_tag_cannot_be_added_to_monitor(qapp):
    tab = BrowseTab()
    tab.load_tree(_tree())
    _select_path(tab, "Pump01.Cmd")
    panel = _panel(tab)

    assert panel._is_write is True
    assert panel._add_btn.isEnabled() is False


def test_tree_plus_button_adds_to_monitor_without_navigating(qapp):
    """Clicking the tree's per-row '+' action must add the tag to the
    Monitor watch list via add_to_monitor_requested WITHOUT switching tabs."""
    tab = BrowseTab()
    tab.load_tree(_tree())

    _select_path(tab, "PIT204.PV")
    item = tab.tree.currentItem()
    assert tab.tree.headerItem().text(3) == "Monitor"
    assert item.text(3) == "+", "Leaf tag should show '+' in Monitor column"

    received = []
    tab.add_to_monitor_requested.connect(received.append)
    tab._on_tree_item_clicked(item, 3)
    assert received == ["PIT204.PV"]


def test_udts_collapsed_after_load(qapp):
    tab = BrowseTab()
    tab.load_tree(_tree())
    parent = _find_tree_item(tab, "PIT204")
    assert parent is not None
    assert not parent.isExpanded()


def test_search_finds_udt_parent_and_shows_all_children(qapp):
    """When filtering for a UDT parent name, ALL children must be visible
    (not filtered individually)."""
    tab = BrowseTab()
    tab.load_tree(_tree())

    tab.search_input.setText("PIT204")
    # The UDT parent "PIT204" should be visible and expanded.
    parent = _find_tree_item(tab, "PIT204")
    child_pv = _find_tree_item(tab, "PIT204.PV")
    child_sts = _find_tree_item(tab, "PIT204.Sts")

    assert parent is not None and not parent.isHidden()
    assert child_pv is not None and not child_pv.isHidden()
    assert child_sts is not None and not child_sts.isHidden()


def test_search_finds_child_and_shows_parent_but_not_siblings(qapp):
    """When filtering for a child tag name, the parent and matching child
    must be visible; non-matching siblings hidden."""
    tab = BrowseTab()
    tab.load_tree(_tree())

    tab.search_input.setText("PV")
    parent = _find_tree_item(tab, "PIT204")
    child_pv = _find_tree_item(tab, "PIT204.PV")
    child_sts = _find_tree_item(tab, "PIT204.Sts")
    ft101 = _find_tree_item(tab, "FT101")

    assert parent is not None and not parent.isHidden()
    assert child_pv is not None and not child_pv.isHidden()
    assert child_sts is not None and child_sts.isHidden()
    assert ft101 is not None and ft101.isHidden()


def test_search_wildcard_prefix(qapp):
    tab = BrowseTab()
    tab.load_tree(_tree())
    tab.search_input.setText("PIT*")
    pit = _find_tree_item(tab, "PIT204")
    ft101 = _find_tree_item(tab, "FT101")
    assert pit is not None and not pit.isHidden()
    assert ft101 is not None and ft101.isHidden()


def test_search_multi_term_or_with_wildcards(qapp):
    tab = BrowseTab()
    tab.load_tree(_tree())
    tab.search_input.setText("PIT*, Facility*")
    pit = _find_tree_item(tab, "PIT204")
    facility = _find_tree_item(tab, "Facility101")
    ft101 = _find_tree_item(tab, "FT101")
    assert pit is not None and not pit.isHidden()
    assert facility is not None and not facility.isHidden()
    assert ft101 is not None and ft101.isHidden()


def test_clear_search_restores_hidden_children_and_expand(qapp):
    """After filtering then clearing, nested UDT children must be visible
    again so expand/collapse works without reconnecting."""
    tab = BrowseTab()
    tab.load_tree(_tree())
    tab.search_input.setText("PIT*")
    parent = _find_tree_item(tab, "PIT204")
    assert parent is not None
    tab.search_input.clear()
    child_pv = _find_tree_item(tab, "PIT204.PV")
    child_sts = _find_tree_item(tab, "PIT204.Sts")
    assert child_pv is not None and not child_pv.isHidden()
    assert child_sts is not None and not child_sts.isHidden()
    tab.tree.expandAll()
    assert parent.isExpanded()


def test_search_clear_button_clears_filter(qapp):
    tab = BrowseTab()
    tab.load_tree(_tree())
    tab.search_input.setText("PIT*")
    qapp.processEvents()
    assert not tab.search_box.clear_btn.isHidden()
    tab.search_box.clear_btn.click()
    assert tab.search_input.text() == ""
    ft101 = _find_tree_item(tab, "FT101")
    assert ft101 is not None and not ft101.isHidden()


def _find_tree_item(tab, tag):
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
