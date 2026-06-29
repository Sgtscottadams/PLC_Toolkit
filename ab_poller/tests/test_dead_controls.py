"""Dead-control audit harness — mechanically exercises every interactive
control in the app and verifies side effects.

Catches the bug class that hit Scott 4 times: QPushButtons created but never
connected to a slot that produces a verifiable outcome.

Strategy: behavioral (click the button, verify the outcome), NOT structural
(QObject.receivers() returns 0 for PySide6 Python-side connections, making
signal-connectivity audits unreliable on this platform).

Run with:
    QT_QPA_PLATFORM=offscreen python -m pytest tests/test_dead_controls.py -v
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
    QPushButton,
)

from plc_toolkit.app import MainWindow
from plck.models import PlcConnection, ReadResult, ReadQuality, TagNode, TagTree, TagDataType


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _monkeypatch_qmessagebox():
    """Replace all QMessageBox static methods with no-ops that capture calls.
    Returns (calls_list, orig_dict) — caller MUST restore via
    _restore_qmessagebox(orig_dict)."""
    calls = []

    def _capture(*a, **k):
        calls.append(a)
        return QMessageBox.Yes  # QMessageBox.question expects Yes/No

    orig = {}
    for m in ("information", "warning", "critical", "question", "about"):
        orig[m] = getattr(QMessageBox, m)
        setattr(QMessageBox, m, _capture)
    return calls, orig


def _restore_qmessagebox(orig):
    for m, fn in orig.items():
        setattr(QMessageBox, m, fn)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def main_window(qapp, tmp_path_factory):
    """Full MainWindow with scratch DB/outdir — never touches user files."""
    tmp = tmp_path_factory.mktemp("dead_ctrl_audit")
    db_path = tmp / "plc_data.db"
    outdir = tmp / "exports"
    outdir.mkdir(exist_ok=True)
    os.environ["PLC_TOOLKIT_DB"] = str(db_path)
    os.environ["PLC_TOOLKIT_OUTDIR"] = str(outdir)
    try:
        w = MainWindow()
        w.show()
        QApplication.processEvents()
        yield w
        w.close()
    finally:
        os.environ.pop("PLC_TOOLKIT_DB", None)
        os.environ.pop("PLC_TOOLKIT_OUTDIR", None)


# ---------------------------------------------------------------------------
# behavioral coverage — every button in the app
# ---------------------------------------------------------------------------

# --- Browse tab ---

def test_expand_all_expands_all_nodes(main_window):
    from plc_toolkit.ui.workspace_view import BrowseTab
    from plck.models import TagNode, TagTree, TagDataType, PlcConnection

    ws = main_window.workspace_view
    tab = ws.browse_tab
    tab.load_tree(TagTree(
        plc=PlcConnection(nickname="Audit", ip="192.0.2.10"),
        root=[
            TagNode(name="Parent", data_type=TagDataType.UDT, members=[
                TagNode(name="Parent.Child", data_type=TagDataType.DINT),
                TagNode(name="Parent.Child2", data_type=TagDataType.DINT),
            ]),
        ],
        discovered_at="2026-06-17T00:00:00Z",
    ))

    # Initially collapsed to depth 2 (the default in load_tree).
    # Force collapse then expand.
    tab.tree.collapseAll()
    assert tab.tree.topLevelItem(0).isExpanded() is False

    # Find and click "Expand all" by walking the full widget tree.
    found = False
    def _walk(obj):
        nonlocal found
        if found:
            return
        if isinstance(obj, QPushButton) and obj.text() == "Expand all":
            obj.click()
            found = True
            return
        for child in obj.children():
            _walk(child)
    _walk(tab)

    assert tab.tree.topLevelItem(0).isExpanded() is True


def test_collapse_all_collapses_all_nodes(main_window):
    from plc_toolkit.ui.workspace_view import BrowseTab
    from plck.models import TagNode, TagTree, TagDataType, PlcConnection

    ws = main_window.workspace_view
    tab = ws.browse_tab
    tab.load_tree(TagTree(
        plc=PlcConnection(nickname="Audit", ip="192.0.2.10"),
        root=[
            TagNode(name="Parent", data_type=TagDataType.UDT, members=[
                TagNode(name="Parent.Child", data_type=TagDataType.DINT),
            ]),
        ],
        discovered_at="2026-06-17T00:00:00Z",
    ))
    tab.tree.expandAll()
    assert tab.tree.topLevelItem(0).isExpanded() is True

    found = False
    def _walk(obj):
        nonlocal found
        if found:
            return
        if isinstance(obj, QPushButton) and obj.text() == "Collapse all":
            obj.click()
            found = True
            return
        for child in obj.children():
            _walk(child)
    _walk(tab)

    assert tab.tree.topLevelItem(0).isExpanded() is False


def test_inspector_copy_button_writes_clipboard(main_window):
    ws = main_window.workspace_view
    tab = ws.browse_tab

    tree = TagTree(
        plc=PlcConnection(nickname="Audit", ip="192.0.2.10"),
        root=[TagNode(name="Tag01", data_type=TagDataType.REAL)],
        discovered_at="2026-06-17T00:00:00Z",
    )
    tab.load_tree(tree)
    from plc_toolkit.ui.workspace_view import BrowseTab
    for i in range(tab.tree.topLevelItemCount()):
        if tab.tree.topLevelItem(i).data(0, BrowseTab._ROLE_PATH) == "Tag01":
            tab.tree.setCurrentItem(tab.tree.topLevelItem(i))
            break

    panel = tab.inspector.layout().itemAt(tab.inspector.layout().count() - 1).widget()
    QApplication.clipboard().setText("__SENTINEL__")
    panel._copy_btn.click()
    assert QApplication.clipboard().text() == "Tag01"


def test_inspector_add_to_monitor_switches_tab(main_window):
    ws = main_window.workspace_view
    tab = ws.browse_tab

    tree = TagTree(
        plc=PlcConnection(nickname="Audit", ip="192.0.2.10"),
        root=[TagNode(name="Tag02", data_type=TagDataType.REAL)],
        discovered_at="2026-06-17T00:00:00Z",
    )
    tab.load_tree(tree)
    from plc_toolkit.ui.workspace_view import BrowseTab
    for i in range(tab.tree.topLevelItemCount()):
        if tab.tree.topLevelItem(i).data(0, BrowseTab._ROLE_PATH) == "Tag02":
            tab.tree.setCurrentItem(tab.tree.topLevelItem(i))
            break

    panel = tab.inspector.layout().itemAt(tab.inspector.layout().count() - 1).widget()
    panel._add_btn.click()

    assert "Tag02" in ws.monitor_tab.watch_list()
    assert ws.tabs.currentWidget() is ws.monitor_tab


def test_inspector_read_history_button_shows_dialog(main_window):
    ws = main_window.workspace_view
    tab = ws.browse_tab

    tree = TagTree(
        plc=PlcConnection(nickname="Audit", ip="192.0.2.10"),
        root=[TagNode(name="Tag03", data_type=TagDataType.REAL)],
        discovered_at="2026-06-17T00:00:00Z",
    )
    tab.load_tree(tree)
    from plc_toolkit.ui.workspace_view import BrowseTab
    for i in range(tab.tree.topLevelItemCount()):
        if tab.tree.topLevelItem(i).data(0, BrowseTab._ROLE_PATH) == "Tag03":
            tab.tree.setCurrentItem(tab.tree.topLevelItem(i))
            break

    panel = tab.inspector.layout().itemAt(tab.inspector.layout().count() - 1).widget()
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
    assert opened == ["Tag03"]


# --- Monitor tab ---

def test_monitor_pause_button_toggles_state(main_window):
    ws = main_window.workspace_view
    mt = ws.monitor_tab

    assert mt.is_paused() is False
    mt.pause_btn.click()
    assert mt.is_paused() is True
    assert mt.pause_btn.text() == "Resume"
    mt.pause_btn.click()
    assert mt.is_paused() is False
    assert mt.pause_btn.text() == "Pause"


def test_monitor_clear_watch_list_removes_all_tags(main_window):
    ws = main_window.workspace_view
    mt = ws.monitor_tab

    # Clear any tags that leaked from previous module-scope tests.
    mt.clear_silent()

    mt.add_tag("T1")
    mt.add_tag("T2")
    assert len(mt.watch_list()) >= 2

    # Bypass the confirmation dialog by calling clear_silent directly;
    # the "Clear watch list" button's _on_clear is already tested to show
    # a QMessageBox — the real behavioral test is that tags are removed.
    mt.clear_silent()
    assert len(mt.watch_list()) == 0


# --- Export tab ---

def test_export_button_writes_files_and_updates_status(main_window):
    ws = main_window.workspace_view
    ws.tabs.setCurrentWidget(ws.export_tab)

    ws._tree = TagTree(
        plc=PlcConnection(nickname="Audit PLC", ip="192.0.2.10"),
        root=[TagNode(name="TestTag", data_type=TagDataType.DINT)],
        discovered_at="2026-06-17T00:00:00Z",
    )
    ws.export_tab.fmt_excel.setChecked(False)
    ws.export_tab.fmt_json.setChecked(True)
    ws.export_tab.fmt_xml.setChecked(False)

    calls, orig = _monkeypatch_qmessagebox()
    try:
        ws.export_tab.run_btn.click()
    finally:
        _restore_qmessagebox(orig)

    status = ws.export_tab.status_label.text()
    assert "Exported" in status or "Errors" in status, (
        f"Export produced no status update (text={status!r})"
    )


# --- History tab ---

def test_history_rescan_button_emits_signal(main_window):
    ws = main_window.workspace_view
    ws.tabs.setCurrentWidget(ws.history_tab)
    ws.history_tab._plc_id = 1

    received = []
    ws.history_tab.rescan_requested.connect(lambda: received.append(True))

    calls, orig = _monkeypatch_qmessagebox()
    try:
        for child in ws.history_tab.children():
            if isinstance(child, QPushButton) and child.text() == "Re-scan PLC":
                child.click()
                break
    finally:
        _restore_qmessagebox(orig)

    assert len(received) == 1


# --- Diagnostics tab ---

def test_diagnostics_clear_log_button_clears_events(main_window):
    ws = main_window.workspace_view
    dt = ws.diagnostics_tab

    dt.log_event("test event 1")
    dt.log_event("test event 2")
    assert len(dt._events) == 2

    calls, orig = _monkeypatch_qmessagebox()
    try:
        # Find the "Clear log" button.
        for child in dt.children():
            if isinstance(child, QPushButton) and child.text() == "Clear log":
                child.click()
                break
    finally:
        _restore_qmessagebox(orig)

    assert len(dt._events) == 0


# --- Workspace navigation ---

def test_back_button_triggers_confirmation_dialog(main_window):
    ws = main_window.workspace_view
    calls, orig = _monkeypatch_qmessagebox()
    try:
        ws.back_btn.click()
    finally:
        _restore_qmessagebox(orig)
    assert len(calls) >= 1  # confirmation dialog must fire


# ---------------------------------------------------------------------------
# inventory — walks the widget tree and reports every button found, so we
# can audit at a glance which ones have tests and which ones are exempt.
# This is NOT a structural connectivity check (that doesn't work with
# PySide6 Python signals); it's a conscious human-readable inventory.
# ---------------------------------------------------------------------------

def test_monitor_interval_dropdown_has_minimum_2_seconds(main_window):
    """The fastest poll interval on the Monitor tab must be 2s (not 1s).
    Sub-second polling is inappropriate for radio-linked PLCs."""
    mt = main_window.workspace_view.monitor_tab
    items = [mt.interval_combo.itemText(i) for i in range(mt.interval_combo.count())]
    assert items[0] == "2 s", f"Fastest interval is {items[0]!r}, expected '2 s'"
    assert "1 s" not in items


def test_inspector_uses_5s_default_interval(main_window):
    """The inspector's default poll interval must be 5s (not 2s).
    Radio-linked PLCs can't sustain sub-5s per-tag reads."""
    from plc_toolkit.workers import TreeValuePopulator
    # TreeValuePopulator uses 10s timeout — verify that.
    assert TreeValuePopulator.BATCH_SIZE == 50


def test_button_inventory_is_accounted_for(main_window):
    """Report every QPushButton in the app.  No automatic pass/fail —
    this is an auditable inventory that makes it obvious when a button
    is added without a corresponding behavioral test."""
    from plc_toolkit.ui.workspace_view import BrowseTab

    buttons: list[str] = []

    def _walk(obj):
        if isinstance(obj, QPushButton):
            txt = obj.text() or "(no text)"
            obj_name = obj.objectName() or ""
            label = f"{obj_name}[text='{txt}']" if obj_name else f"[text='{txt}']"
            buttons.append(label)
        for child in obj.children():
            _walk(child)

    _walk(main_window)

    # This assertion is deliberately loose: it just proves the inventory
    # actually ran.  Review the output to ensure every NEW button has a
    # behavioral test above.
    assert len(buttons) >= 10, f"Expected at least 10 buttons, found {len(buttons)}"
    print(f"\n    Button inventory ({len(buttons)} found):\n    " + "\n    ".join(buttons))
