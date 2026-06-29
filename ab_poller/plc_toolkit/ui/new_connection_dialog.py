"""New Connection dialog.

Modal dialog for entering a new PLC connection. Validates inputs and
emits `connection_accepted(PlcConnection)` when the user clicks
"Save & connect".

If the user came here from a Discover result, the dialog opens
pre-populated with the discovered IP. The "Save & connect" button is
the only path that writes to the DB.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

import plck
from plck.comms import PLCClient
from plck.device_filter import is_tag_readable_controller, unsupported_device_message
from plck.errors import PlcError, PlcTimeout
from plck.models import PlcConnection


class _TestSignals(QObject):
    """Signals from the test-connection worker thread."""

    finished = Signal(str, str)  # state: success|error, message
    failed = Signal(str)         # fatal error string


class _TestWorker(QThread):
    """Run a test-connection CIP query on a worker thread."""

    def __init__(self, plc: PlcConnection, timeout_s: float = 5.0) -> None:
        super().__init__()
        self.plc = plc
        self.timeout_s = timeout_s
        self.signals = _TestSignals()

    def run(self) -> None:
        try:
            client = PLCClient(self.plc, timeout_s=self.timeout_s)
            client.get_device_info()
            d = self.plc
            msg = (
                f"{d.product_name or '(unknown)'} — revision {d.revision or '?'} "
                f"(response: vendor={d.vendor or '?'})"
            )
            self.signals.finished.emit("success", msg)
        except PlcTimeout as e:
            self.signals.finished.emit("error", f"Timeout: {e}")
        except PlcError as e:
            self.signals.finished.emit("error", f"PLC error: {e}")
        except Exception as e:
            self.signals.failed.emit(f"Unexpected: {e!r}")


class NewConnectionDialog(QDialog):
    """The '+ Connect to a new PLC' dialog."""

    connection_accepted = Signal(object)  # PlcConnection

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        default_ip: str = "",
        default_nickname: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connect to a new PLC")
        self.setModal(True)
        self.resize(440, 480)

        self._test_worker: Optional[_TestWorker] = None
        # Holds the last-tested PlcConnection so we can preserve any
        # discovered vendor/revision when the user clicks Save.
        self._tested_plc: Optional[PlcConnection] = None

        self.nickname_input = QLineEdit()
        self.nickname_input.setPlaceholderText("e.g. Compressor Skid A")
        self.nickname_input.setText(default_nickname)

        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("10.20.30.41")
        self.ip_input.setText(default_ip)

        self.slot_input = QSpinBox()
        self.slot_input.setRange(0, 16)
        self.slot_input.setValue(0)
        self.slot_input.setToolTip(
            "Processor slot. Most ControlLogix/CompactLogix are slot 0."
        )

        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(44818)
        self.port_input.setToolTip(
            "EtherNet/IP port. Default 44818 — change only if your PLC is "
            "on a non-standard port."
        )

        self.cip_path_input = QLineEdit()
        self.cip_path_input.setPlaceholderText("(leave blank to use slot only)")
        self.cip_path_input.setToolTip(
            "Backplane CIP path. Leave blank unless you need a multi-hop "
            "route (e.g. through a 1756-ENBT gateway). Most installations don't."
        )

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setVisible(False)
        self.result_frame = QFrame()
        self.result_frame.setVisible(False)
        self.result_frame.setObjectName("testResultFrame")
        rf = QVBoxLayout(self.result_frame)
        rf.setContentsMargins(10, 8, 10, 8)
        self.result_title = QLabel("")
        self.result_title.setObjectName("testResultTitle")
        rf.addWidget(self.result_title)
        rf.addWidget(self.result_label)

        self.test_btn = QPushButton("Test connection")
        self.test_btn.clicked.connect(self._on_test)
        self.save_btn = QPushButton("Save && connect")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._on_save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.test_btn)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self.save_btn)

        form = QFormLayout()
        form.addRow("Nickname (optional)", self.nickname_input)
        form.addRow("IP address", self.ip_input)
        form.addRow("Processor slot", self.slot_input)
        form.addRow("Port", self.port_input)
        adv_label = QLabel("CIP path (advanced)")
        adv_label.setToolTip(self.cip_path_input.toolTip())
        form.addRow(adv_label, self.cip_path_input)

        outer = QVBoxLayout(self)
        outer.addLayout(form)
        outer.addWidget(self.result_frame)
        outer.addStretch()
        outer.addLayout(btn_row)

    def _build_plc(self) -> PlcConnection:
        cip = self.cip_path_input.text().strip() or None
        return PlcConnection(
            nickname=self.nickname_input.text().strip(),
            ip=self.ip_input.text().strip(),
            slot=self.slot_input.value(),
            port=self.port_input.value(),
            cip_path=cip,
        )

    def _on_test(self) -> None:
        plc = self._build_plc()
        if not plc.is_valid():
            self._show_result(
                "error", "Invalid input",
                "IP address is required.",
            )
            return
        self._show_result("pending", "Testing connection…", "")
        self.test_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        if self._test_worker is not None and self._test_worker.isRunning():
            self._test_worker.quit()
            self._test_worker.wait(2000)
        self._tested_plc = plc
        self._test_worker = _TestWorker(plc, timeout_s=5.0)
        self._test_worker.signals.finished.connect(self._on_test_finished)
        self._test_worker.signals.failed.connect(self._on_test_failed)
        self._test_worker.start()

    def _on_test_finished(self, state: str, message: str) -> None:
        self.test_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        if state == "success":
            plc = self._tested_plc
            if plc is not None and not is_tag_readable_controller(
                plc.product_name, plc.vendor,
            ):
                self._show_result(
                    "error",
                    "Unsupported device",
                    unsupported_device_message(plc.product_name),
                )
                return
            self._show_result("success", "Connection successful", message)
        else:
            self._show_result("error", "Connection failed", message)

    def _on_test_failed(self, message: str) -> None:
        self.test_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self._show_result("error", "Connection failed", message)

    def _show_result(self, state: str, title: str, message: str) -> None:
        """state is 'pending' | 'success' | 'error'."""
        self.result_frame.setVisible(True)
        self.result_label.setVisible(bool(message))
        self.result_label.setText(message)
        self.result_frame.setProperty("dataState", state)
        self.result_frame.style().unpolish(self.result_frame)
        self.result_frame.style().polish(self.result_frame)
        self.result_title.setText(title)

    def _on_save(self) -> None:
        plc = self._build_plc()
        if not plc.is_valid():
            self._show_result(
                "error", "Invalid input",
                "IP address is required.",
            )
            return
        # If we previously tested, copy discovered fields across.
        if self._tested_plc is not None:
            plc.vendor = self._tested_plc.vendor
            plc.product_name = self._tested_plc.product_name
            plc.revision = self._tested_plc.revision
            plc.serial_number = self._tested_plc.serial_number
            plc.device_id = self._tested_plc.product_name or plc.ip
            if plc.product_name and not is_tag_readable_controller(
                plc.product_name, plc.vendor,
            ):
                self._show_result(
                    "error",
                    "Unsupported device",
                    unsupported_device_message(plc.product_name),
                )
                return
        self.connection_accepted.emit(plc)
        self.accept()

    def accept(self) -> None:  # noqa: D401
        if self._test_worker is not None and self._test_worker.isRunning():
            self._test_worker.quit()
            self._test_worker.wait(2000)
        super().accept()
