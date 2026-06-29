from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from plc_toolkit.ui.workspace_view import MonitorTab


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_monitor_add_tag_respects_max(qapp, monkeypatch):
    tab = MonitorTab(history_samples=60)
    tab.MONITOR_MAX_TAGS = 2

    warnings: list[str] = []

    def fake_warning(_self, _title, msg):
        warnings.append(msg)

    monkeypatch.setattr(
        "plc_toolkit.ui.workspace_view.QMessageBox.warning", fake_warning,
    )

    assert tab.add_tag("A", "?") is True
    assert tab.add_tag("B", "?") is True
    assert tab.add_tag("C", "?") is False
    assert tab.watch_list() == ["A", "B"]
    assert warnings


def test_monitor_history_depth_from_settings(qapp):
    tab = MonitorTab(history_samples=120)
    tab.add_tag("T1", "REAL")
    entry = tab._watch["T1"]
    assert entry["samples"].maxlen == 120
    assert entry["sample_times"].maxlen == 120

    tab.set_history_samples(240)
    assert tab._history_samples == 240
    assert tab._watch["T1"]["samples"].maxlen == 240


def test_export_monitor_history_writes_xlsx_and_csv(tmp_path: Path):
    pytest.importorskip("openpyxl")
    from plck.export import export_monitor_history

    watch = {
        "Facility.PIT204.PV": {
            "data_type": "REAL",
            "last_value": 42.0,
            "last_quality": "Good",
            "samples": [41.0, 42.0],
            "sample_times": ["2026-06-24 - 10:00:00", "2026-06-24 - 10:00:05"],
        },
    }
    paths = export_monitor_history(watch, nickname="SkidA", out_dir=tmp_path)
    assert len(paths) == 1
    xlsx = paths[0]
    assert xlsx.suffix == ".xlsx"
    assert xlsx.exists()
