"""plc_toolkit.workers — QThread-based workers for PLC I/O.

The single most important rule for the GUI: the main Qt thread NEVER
blocks on PLC I/O. All reads, writes, and discovery go through a
QThread and emit Qt signals back to the UI. This is what keeps the
GUI responsive during a 30-second subnet scan or a 5,000-tag
discovery.

Three workers:
    DiscoveryWorker -- one-shot, runs plck.discovery.discover_tags
    MonitorWorker   -- continuous, reads a watch list every N seconds
    SubnetDiscoveryWorker -- one-shot, runs plck.comms.PLCClient.discover

Each worker exposes Qt signals (PySideSignal) for progress, success,
and failure. UI code connects to these signals and updates widgets.
"""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal

import plck
from plck.comms import PLCClient
from plck.device_filter import is_tag_readable_controller
from plck.errors import PlcError
from plck.models import PlcConnection, ReadResult, TagTree


class _DiscoverySignals(QObject):
    """Signals emitted by DiscoveryWorker. Defined on a QObject because
    QThread itself doesn't carry signals."""

    started = Signal()
    progress = Signal(str)  # human-readable status line
    finished = Signal(object)  # TagTree
    failed = Signal(str)  # error message
    unsupported = Signal(object)  # PlcConnection — device type not tag-readable


class DiscoveryWorker(QThread):
    """Run plck.discovery.discover_tags on a worker thread."""

    def __init__(self, plc: PlcConnection, timeout_s: float = 5.0) -> None:
        super().__init__()
        self.plc = plc
        self.timeout_s = timeout_s
        self._cancelled = False
        self.signals = _DiscoverySignals()

    def stop(self) -> None:
        self._cancelled = True

    # Tag enumeration over a slow / radio-linked PLC can take far longer
    # than a quick connection test, so discovery uses a generous floor.
    _DISCOVERY_TIMEOUT_FLOOR_S = 30.0

    def run(self) -> None:
        if self._cancelled:
            return
        self.signals.started.emit()
        timeout = max(self.timeout_s, self._DISCOVERY_TIMEOUT_FLOOR_S)
        client = PLCClient(self.plc, timeout_s=timeout)
        try:
            self.signals.progress.emit(f"Connecting to {client.plc.ip}…")
            client.get_device_info()
            if self._cancelled:
                return
            # Block non-Logix devices (MicroLogix, SLC, PanelView, etc.)
            # here — once device info is known — so a manually-added or
            # direct connection gets a clear "not supported" message
            # instead of a confusing tag-discovery timeout.
            if not is_tag_readable_controller(
                self.plc.product_name, self.plc.vendor
            ):
                if not self._cancelled:
                    self.signals.unsupported.emit(self.plc)
                return
            self.signals.progress.emit(
                "Querying tag list (this can take a while on large programs)…"
            )
            tree = plck.discovery.discover_tags(client)
            if self._cancelled:
                return
            self.signals.progress.emit(
                f"Discovered {tree.count()} tags ({tree.leaf_count()} leaves) in "
                f"{tree.discovery_duration_s:.1f}s"
            )
            self.signals.finished.emit(tree)
        except PlcError as e:
            if not self._cancelled:
                self.signals.failed.emit(str(e))
        except Exception as e:  # last-resort safety net
            if not self._cancelled:
                self.signals.failed.emit(f"Unexpected error: {e!r}")


class _MonitorSignals(QObject):
    started = Signal()
    sample = Signal(list)  # list[ReadResult] for this poll
    failed = Signal(str)
    stopped = Signal()


class MonitorWorker(QThread):
    """Read a list of tags on a fixed interval. Emits one sample per cycle.

    The GUI builds the watch list (list[str] of tag paths), passes it
    in, and the worker reads all of them with a single pylogix
    multi-tag Read() per cycle. This is the cheap, fast path —
    one CIP packet per cycle, not one per tag.
    """

    def __init__(
        self,
        plc: PlcConnection,
        tags: list[str],
        interval_s: float = 5.0,
        timeout_s: float = 5.0,
    ) -> None:
        super().__init__()
        self.plc = plc
        self.tags = list(tags)
        self.interval_s = float(interval_s)
        self.timeout_s = timeout_s
        self._running = True
        self.signals = _MonitorSignals()

    def stop(self) -> None:
        self._running = False

    def set_tags(self, tags: list[str]) -> None:
        """Replace the watch list. Takes effect on the next cycle."""
        self.tags = list(tags)

    def run(self) -> None:
        self.signals.started.emit()
        client = PLCClient(self.plc, timeout_s=self.timeout_s)
        while self._running:
            if not self.tags:
                time.sleep(min(0.5, self.interval_s))
                continue
            try:
                results = client.read_many(self.tags)
                self.signals.sample.emit(results)
            except PlcError as e:
                self.signals.failed.emit(str(e))
                # Back off so we don't hammer a dead PLC.
                time.sleep(self.interval_s)
            time.sleep(self.interval_s)
        self.signals.stopped.emit()


class _SubnetSignals(QObject):
    started = Signal()
    progress = Signal(str)
    finished = Signal(list)  # list[dict] per plck.comms.PLCClient.discover
    failed = Signal(str)


class SubnetDiscoveryWorker(QThread):
    """Run subnet discovery (UDP broadcast + direct TCP scan)."""

    def __init__(
        self,
        plc: PlcConnection,
        timeout_s: float = 2.0,
        subnet_cidr: Optional[str] = None,
        probe_timeout_s: float = 2.0,
        max_workers: int = 20,
    ) -> None:
        super().__init__()
        self.plc = plc
        self.timeout_s = timeout_s
        self.subnet_cidr = subnet_cidr
        self.probe_timeout_s = probe_timeout_s
        self.max_workers = max_workers
        self.signals = _SubnetSignals()

    def run(self) -> None:
        self.signals.started.emit()
        client = PLCClient(self.plc, timeout_s=self.timeout_s)
        try:
            if self.subnet_cidr:
                self.signals.progress.emit(
                    f"Scanning {self.subnet_cidr}…"
                )
            else:
                self.signals.progress.emit(
                    f"Broadcasting CIP ListIdentity on 255.255.255.255:{client.plc.port}…"
                )
            devices = client.discover(
                subnet_cidr=self.subnet_cidr,
                progress_cb=lambda msg: self.signals.progress.emit(msg),
                probe_timeout_s=self.probe_timeout_s,
                max_workers=self.max_workers,
            )
            self.signals.progress.emit(f"Found {len(devices)} device(s) on the subnet.")
            self.signals.finished.emit(devices)
        except PlcError as e:
            self.signals.failed.emit(str(e))
        except Exception as e:
            self.signals.failed.emit(f"Unexpected error: {e!r}")


# -- Inspector (single-tag, on-demand, 2s poll) --------------------------


class _InspectorSignals(QObject):
    sample = Signal(object)  # ReadResult
    failed = Signal(str)
    stopped = Signal()


class InspectorWorker(QThread):
    """Read ONE tag on a short interval (2s) while the operator is
    inspecting it. Stops when the operator picks a different tag or
    navigates away.

    This is the cheap one-tag-read path; it does NOT participate in
    the Monitor watch list poll cycle.
    """

    def __init__(
        self,
        plc: PlcConnection,
        tag: str,
        interval_s: float = 2.0,
        timeout_s: float = 5.0,
    ) -> None:
        super().__init__()
        self.plc = plc
        self.tag = tag
        self.interval_s = float(interval_s)
        self.timeout_s = timeout_s
        self._running = True
        self.signals = _InspectorSignals()

    def stop(self) -> None:
        self._running = False

    def set_tag(self, tag: str) -> None:
        self.tag = tag

    def run(self) -> None:
        client = PLCClient(self.plc, timeout_s=self.timeout_s)
        while self._running and self.tag:
            try:
                r = client.read(self.tag)
                self.signals.sample.emit(r)
            except PlcError as e:
                self.signals.failed.emit(str(e))
            # Sleep, but break out if stopped mid-sleep.
            slept = 0.0
            while self._running and slept < self.interval_s:
                time.sleep(0.1)
                slept += 0.1
        self.signals.stopped.emit()


# -- TreeValuePopulator — one-shot batch read of all leaf tags -------------


class _ValuePopulatorSignals(QObject):
    started = Signal()
    chunk_loaded = Signal(list)  # list[ReadResult]
    finished = Signal()
    failed = Signal(str)
    progress = Signal(str)


class TreeValuePopulator(QThread):
    """One-shot: read all leaf tag paths in batches and emit each chunk.

    Used to auto-populate the Browse tree's "Value" column after discovery
    completes, so the operator sees live values without clicking every tag.

    Reads tags in batches of 50 (one CIP multi-tag request per batch) to keep
    individual requests small on slow radio links.
    """

    BATCH_SIZE = 50

    def __init__(
        self,
        plc: PlcConnection,
        tags: list[str],
        timeout_s: float = 10.0,
    ) -> None:
        super().__init__()
        self.plc = plc
        self.tags = list(tags)
        self.timeout_s = timeout_s
        self._running = True
        self._pos = 0
        self.signals = _ValuePopulatorSignals()

    def stop(self) -> None:
        self._running = False

    def set_tags(self, tags: list[str]) -> None:
        """Replace the tag list (e.g. filter reprioritize on the Browse tab)."""
        self.tags = list(tags)
        self._pos = 0

    def run(self) -> None:
        self.signals.started.emit()
        client = PLCClient(self.plc, timeout_s=self.timeout_s)
        errors = 0
        try:
            while self._running:
                tags = self.tags
                if self._pos >= len(tags):
                    break
                batch = tags[self._pos : self._pos + self.BATCH_SIZE]
                self._pos += self.BATCH_SIZE
                if not batch:
                    break
                try:
                    results = client.read_many(batch)
                    self.signals.chunk_loaded.emit(results)
                except PlcError as e:
                    errors += len(batch)
                    self.signals.progress.emit(
                        f"Batch failed: {e}"
                    )
                self.signals.progress.emit(
                    f"Populating values: {min(self._pos, len(tags))}/{len(tags)}"
                )
            if self._pos >= len(self.tags):
                if errors:
                    self.signals.failed.emit(
                        f"Value population complete with {errors} error(s) / "
                        f"{len(self.tags)} tag(s)"
                    )
                else:
                    self.signals.finished.emit()
        except Exception as e:
            self.signals.failed.emit(f"Value population failed: {e!r}")
