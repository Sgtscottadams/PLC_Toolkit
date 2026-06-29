"""Connection Manager table sorting."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from plck.models import PlcConnection
from plc_toolkit.ui.connection_view import ConnectionView


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeDb:
    def list_plcs(self):
        return [
            PlcConnection(nickname="Zebra", ip="10.0.0.50", slot=0),
            PlcConnection(nickname="Alpha", ip="10.0.0.10", slot=0),
            PlcConnection(nickname="Beta", ip="10.0.0.30", slot=0),
        ]


def test_connection_table_defaults_to_ip_sort(qapp):
    view = ConnectionView(_FakeDb())
    ips = [
        view.table.item(r, view._COL_IP).text()
        for r in range(view.table.rowCount())
    ]
    assert ips == ["10.0.0.10", "10.0.0.30", "10.0.0.50"]


def test_connection_header_click_resorts(qapp):
    view = ConnectionView(_FakeDb())
    view._on_header_clicked(view._COL_NICKNAME)
    nicks = [
        view.table.item(r, view._COL_NICKNAME).text()
        for r in range(view.table.rowCount())
    ]
    assert nicks == ["Alpha", "Beta", "Zebra"]
