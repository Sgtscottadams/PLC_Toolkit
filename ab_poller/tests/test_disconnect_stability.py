"""Disconnect / worker teardown stability tests."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from plck.models import PlcConnection, ReadQuality, ReadResult, TagDataType, TagNode, TagTree
from plc_toolkit.workers import DiscoveryWorker, MonitorWorker


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def test_discovery_worker_stop_is_cooperative():
    worker = DiscoveryWorker(PlcConnection(ip="10.0.0.1"))
    assert hasattr(worker, "stop")
    worker.stop()
    assert worker._cancelled is True


def test_stop_workers_clears_connected_state(qapp, tmp_path):
    from plck.db import DatabaseManager
    from plc_toolkit.ui.workspace_view import WorkspaceView

    db = DatabaseManager(path=str(tmp_path / "disc.db"))
    view = WorkspaceView(db, tmp_path / "exports")
    view._connected = True
    view._plc = PlcConnection(ip="10.0.0.5")
    view._stop_workers()
    assert view._connected is False
    assert view._plc is None


def test_monitor_sample_ignored_after_disconnect(qapp, tmp_path):
    from plck.db import DatabaseManager
    from plc_toolkit.ui.workspace_view import WorkspaceView

    db = DatabaseManager(path=str(tmp_path / "disc.db"))
    view = WorkspaceView(db, tmp_path / "exports")
    view._connected = True
    view.monitor_tab.add_tag("Tag01", data_type=TagDataType.BOOL.value)
    view._connected = False
    before = len(view.monitor_tab.watch_list())
    view._on_monitor_sample([
        ReadResult(
            tag_name="Tag01",
            value=True,
            quality=ReadQuality.GOOD,
            elapsed_ms=1.0,
        )
    ])
    assert len(view.monitor_tab.watch_list()) == before


def test_discovery_finished_guarded_by_epoch(qapp, tmp_path):
    from plck.db import DatabaseManager
    from plc_toolkit.ui.workspace_view import WorkspaceView

    db = DatabaseManager(path=str(tmp_path / "disc.db"))
    view = WorkspaceView(db, tmp_path / "exports")
    plc = PlcConnection(ip="10.0.0.8")
    view._plc = plc
    view._connected = True
    view._connection_epoch = 2
    tree = TagTree(
        plc=plc,
        root=[TagNode(name="A", data_type=TagDataType.BOOL)],
        discovered_at="2026-06-24T12:00:00Z",
    )
    view._on_discovery_finished_guarded(tree, epoch=1)
    assert view._tree is None


def test_disconnect_worker_signals_is_idempotent():
    from plc_toolkit.worker_lifecycle import disconnect_worker_signals

    worker = MonitorWorker(
        PlcConnection(ip="10.0.0.1"),
        tags=["T"],
        interval_s=30.0,
    )
    disconnect_worker_signals(worker)
    disconnect_worker_signals(worker)
