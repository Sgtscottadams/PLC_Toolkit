"""Export tab format defaults when source changes."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from plc_toolkit.ui.workspace_view import ExportTab


def test_watch_list_source_selects_excel_history_only(tmp_path):
    tab = ExportTab(tmp_path / "exports")
    tab.src_watch.setChecked(True)
    tab._sync_history_export_option()
    assert tab.fmt_excel_history.isChecked()
    assert not tab.fmt_excel.isChecked()


def test_tree_source_restores_excel_and_json(tmp_path):
    tab = ExportTab(tmp_path / "exports")
    tab.src_watch.setChecked(True)
    tab._sync_history_export_option()
    tab.src_tree.setChecked(True)
    tab._sync_history_export_option()
    assert tab.fmt_excel.isChecked()
    assert tab.fmt_json.isChecked()
    assert not tab.fmt_excel_history.isChecked()
