"""Tests for the unsupported-device guard on direct/manual connect.

Pins the fix for the MicroLogix (and other non-Logix AB device) loophole:
a direct connection to a blocked device must produce a clear, device-typed
"not supported" message instead of a confusing tag-discovery timeout.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from plck.device_filter import describe_device_type, unsupported_device_message
from plck.models import PlcConnection


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_describe_micrologix():
    assert describe_device_type("1766-L32BWAA").startswith("MicroLogix 1400")


def test_describe_supported_logix():
    assert "CompactLogix" in describe_device_type("1769-L33ER/A")


def test_describe_falls_back_to_raw():
    assert describe_device_type("1747-L552") .startswith("SLC 500")
    assert describe_device_type(None) == "This device"


def test_unsupported_message_names_the_device_type():
    msg = unsupported_device_message("1766-L32BWAA")
    assert "MicroLogix 1400" in msg
    assert "not supported" in msg


def test_discovery_worker_emits_unsupported_for_micrologix(monkeypatch):
    _app()
    from plc_toolkit import workers

    class _FakeClient:
        def __init__(self, plc, timeout_s=5.0):
            self.plc = plc

        def get_device_info(self):
            self.plc.product_name = "1766-L32BWAA"
            self.plc.vendor = 1
            return self.plc

    monkeypatch.setattr(workers, "PLCClient", _FakeClient)

    plc = PlcConnection(ip="10.254.120.99", slot=0)
    worker = workers.DiscoveryWorker(plc)
    captured: dict = {}
    worker.signals.unsupported.connect(lambda p: captured.__setitem__("plc", p))
    worker.signals.finished.connect(lambda t: captured.__setitem__("finished", t))
    worker.signals.failed.connect(lambda m: captured.__setitem__("failed", m))

    # Run synchronously in the test thread (no event loop needed for
    # same-thread direct signal delivery).
    worker.run()

    assert "plc" in captured
    assert captured["plc"].product_name == "1766-L32BWAA"
    assert "finished" not in captured
    assert "failed" not in captured


def test_discovery_worker_proceeds_for_supported_plc(monkeypatch):
    _app()
    from plc_toolkit import workers

    class _FakeTree:
        discovery_duration_s = 0.0

        def count(self):
            return 0

        def leaf_count(self):
            return 0

    sentinel_tree = _FakeTree()

    class _FakeClient:
        def __init__(self, plc, timeout_s=5.0):
            self.plc = plc

        def get_device_info(self):
            self.plc.product_name = "1769-L33ER"
            self.plc.vendor = 1
            return self.plc

    monkeypatch.setattr(workers, "PLCClient", _FakeClient)
    monkeypatch.setattr(
        workers.plck.discovery, "discover_tags", lambda client: sentinel_tree
    )

    plc = PlcConnection(ip="10.254.120.102", slot=0)
    worker = workers.DiscoveryWorker(plc)
    captured: dict = {}
    worker.signals.unsupported.connect(lambda p: captured.__setitem__("unsupported", p))
    worker.signals.finished.connect(lambda t: captured.__setitem__("finished", t))
    worker.run()

    assert captured.get("finished") is sentinel_tree
    assert "unsupported" not in captured
