from __future__ import annotations

from pathlib import Path


WORKSPACE = Path("plc_toolkit/ui/workspace_view.py")
CONNECTION = Path("plc_toolkit/ui/connection_view.py")
WORKERS = Path("plc_toolkit/workers/__init__.py")


def test_workspace_does_not_pass_ui_thread_plcclient_to_workers():
    src = WORKSPACE.read_text(encoding="utf-8")

    assert "self._client = PLCClient(plc" not in src
    assert "DiscoveryWorker(self._client" not in src
    assert "MonitorWorker(\n            self._client" not in src
    assert "InspectorWorker(self._client" not in src


def test_workers_construct_plcclient_inside_worker_run_methods():
    src = WORKERS.read_text(encoding="utf-8")

    assert "def __init__(self, plc: PlcConnection" in src
    assert "client = PLCClient(self.plc" in src


def test_connection_view_does_not_pass_ui_thread_plcclient_to_subnet_worker():
    src = CONNECTION.read_text(encoding="utf-8")

    assert "client = PLCClient(temp" not in src
    assert "SubnetDiscoveryWorker(client" not in src
    # The connection view now opens SubnetScanDialog which manages its own
    # worker. No direct SubnetDiscoveryWorker construction on the UI thread.
    assert "SubnetScanDialog(" in src
