from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from plc_toolkit.ui.chart_dialog import TrendChartWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_samples_at_x_finds_nearest_per_series(qapp):
    chart = TrendChartWidget()
    chart.set_series_names(["A", "B"])
    chart.replace_series_data("A", [("10:00:00", 1.0), ("10:00:05", 2.0), ("10:00:10", 3.0)])
    chart.replace_series_data("B", [("10:00:01", 10.0), ("10:00:06", 20.0)])

    _rect, plot = chart._plot_area()
    mid_x = plot.left() + plot.width() // 2
    rows = chart.samples_at_x(mid_x)
    assert len(rows) == 2
    names = {r[0] for r in rows}
    assert names == {"A", "B"}
    for _name, ts, val in rows:
        assert ts
        assert isinstance(val, float)


def test_stamp_emits_all_series(qapp):
    chart = TrendChartWidget()
    chart.set_series_names(["T1"])
    chart.replace_series_data("T1", [("12:00:00", 42.0)])
    received = []
    chart.stamp_added.connect(received.append)
    _rect, plot = chart._plot_area()
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QPointF, Qt

    pos = QPointF(plot.center())
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        pos,
        pos,
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    chart.mousePressEvent(event)
    assert len(received) == 1
    assert received[0][0][0] == "T1"
