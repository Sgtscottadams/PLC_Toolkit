"""SubnetScanDialog — popup for discovering PLCs on a subnet.

Opens from the Connection Manager's "Discover on subnet" button.
Lets the operator:
  1. Enter a subnet (CIDR, broadcast addr, or host IP)
  2. Click Scan to discover devices via direct TCP probes
  3. Select any number of discovered PLCs with checkboxes
  4. Click "Add selected" to batch-insert them into the saved-connections list
  5. Rescan a different subnet without closing the dialog
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from plck.device_filter import format_device_display


class SubnetScanDialog(QDialog):
    """Modal dialog for subnet discovery with multi-select batch add."""

    # Emitted with (ip, product_name, revision) for each device the operator
    # chose to add.  The caller inserts them into the DB and refreshes the
    # connection list.
    devices_selected = Signal(list)  # list of dicts {ip, product_name, revision}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Subnet Discovery")
        self.resize(700, 500)
        self.setMinimumSize(550, 380)
        self._worker: Optional[object] = None  # SubnetDiscoveryWorker
        self._discovered: list[dict] = []
        self._checkboxes: list[QCheckBox] = []
        self._scanning = False

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # --- Row 1: subnet input + scan button ---
        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("Subnet:"))
        self.subnet_input = QLineEdit()
        self.subnet_input.setPlaceholderText("172.17.117.0/24 or 172.17.117.255")
        self.subnet_input.returnPressed.connect(self._on_scan)
        input_row.addWidget(self.subnet_input, 1)
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.setDefault(True)
        self.scan_btn.clicked.connect(self._on_scan)
        input_row.addWidget(self.scan_btn)
        layout.addLayout(input_row)

        # --- Progress bar ---
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status_label = QLabel("Enter a subnet and click Scan to discover PLCs.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # --- Results table ---
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", "IP Address", "Device", "Revision"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)   # checkbox
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)   # IP
        h.setSectionResizeMode(2, QHeaderView.Stretch)            # Product
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)   # Revision
        layout.addWidget(self.table, 1)

        select_row = QHBoxLayout()
        self.select_all_btn = QPushButton("Select all")
        self.select_all_btn.clicked.connect(self._select_all)
        self.unselect_all_btn = QPushButton("Unselect all")
        self.unselect_all_btn.clicked.connect(self._unselect_all)
        select_row.addWidget(self.select_all_btn)
        select_row.addWidget(self.unselect_all_btn)
        select_row.addStretch()
        layout.addLayout(select_row)
        self._update_select_buttons()

        # --- Bottom buttons ---
        button_box = QDialogButtonBox()
        self.add_btn = button_box.addButton(
            "Add selected", QDialogButtonBox.AcceptRole
        )
        self.add_btn.setEnabled(False)
        button_box.addButton(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self._on_add_selected)
        layout.addWidget(button_box)

    # -- Public -----------------------------------------------------------

    def set_plc_connection(self, plc):
        """Store a reference PlcConnection for slot/port defaults."""
        self._plc = plc

    # -- Slots ------------------------------------------------------------

    def _on_scan(self):
        """Start a subnet scan in a background thread."""
        from plck.models import PlcConnection
        from plc_toolkit.workers import SubnetDiscoveryWorker

        if self._scanning and self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.quit()
            self._worker.wait(2000)
            self._finish_scan_ui()
            self.status_label.setText("Scan cancelled.")
            return

        subnet = self.subnet_input.text().strip()
        if not subnet:
            return

        # Stop any running scan.
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)

        self._clear_results()
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Cancel scan")
        self._scanning = True
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.status_label.setText(f"Scanning {subnet}…")

        temp = PlcConnection(nickname="<scan>", ip="0.0.0.0")
        self._worker = SubnetDiscoveryWorker(
            temp, timeout_s=5.0, subnet_cidr=subnet,
            probe_timeout_s=2.0, max_workers=20,
        )
        self._worker.signals.finished.connect(self._on_scan_finished)
        self._worker.signals.failed.connect(self._on_scan_failed)
        self._worker.signals.progress.connect(self._on_scan_progress)
        self._worker.start()

    def _finish_scan_ui(self) -> None:
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("Scan")
        self._scanning = False
        self.progress.setVisible(False)

    def _on_scan_finished(self, devices: list):
        self._finish_scan_ui()
        self._discovered = devices
        if not devices:
            self.status_label.setText(
                "No tag-readable PLCs found on this subnet.\n\n"
                "PanelViews, switches, and other EtherNet/IP devices are "
                "hidden — only Logix-family controllers appear here.\n\n"
                "Try:\n"
                "• Enter CIDR notation (e.g. 172.17.117.0/24) instead of the "
                "broadcast address alone\n"
                "• Confirm your PC is on the same network as the PLCs\n"
                "• Add a PLC directly with its IP if you already know it\n"
                "• Radio-linked PLCs may need a longer scan — wait for the "
                "full progress bar to finish"
            )
            return

        self.table.setRowCount(len(devices))
        self._checkboxes = []
        for r, d in enumerate(devices):
            cb = QCheckBox()
            self.table.setCellWidget(r, 0, cb)
            self.table.setItem(r, 1, QTableWidgetItem(d["ip"]))
            product = (d.get("product_name") or "").strip()
            self.table.setItem(
                r, 2,
                QTableWidgetItem(
                    format_device_display(product, ip=d["ip"]) or product
                ),
            )
            self.table.setItem(r, 3, QTableWidgetItem(d.get("revision", "")))
            cb.toggled.connect(self._update_add_button)
            self._checkboxes.append(cb)

        self.status_label.setText(
            f"Found {len(devices)} PLC(s). Select the ones to add and click "
            f"\"Add selected\"."
        )
        self._update_select_buttons()

    def _update_select_buttons(self) -> None:
        has_rows = bool(self._checkboxes)
        self.select_all_btn.setEnabled(has_rows)
        self.unselect_all_btn.setEnabled(has_rows)

    def _select_all(self) -> None:
        for cb in self._checkboxes:
            cb.setChecked(True)

    def _unselect_all(self) -> None:
        for cb in self._checkboxes:
            cb.setChecked(False)

    def _on_scan_failed(self, message: str):
        self._finish_scan_ui()
        self.status_label.setText(f"Scan failed: {message}")

    def _on_scan_progress(self, message: str):
        self.status_label.setText(message)
        # Crude progress based on IP count in message.
        import re
        m = re.search(r"(\d+)/(\d+)", message)
        if m:
            current, total = int(m.group(1)), int(m.group(2))
            self.progress.setValue(int(current / total * 100))

    def _update_add_button(self):
        self.add_btn.setEnabled(any(cb.isChecked() for cb in self._checkboxes))

    def _on_add_selected(self):
        selected = [
            d for d, cb in zip(self._discovered, self._checkboxes)
            if cb.isChecked()
        ]
        if not selected:
            return
        ips = ", ".join(d["ip"] for d in selected[:5])
        if len(selected) > 5:
            ips += f", … (+{len(selected) - 5} more)"
        confirm = QMessageBox.question(
            self,
            "Add PLCs to saved connections?",
            f"Add {len(selected)} PLC(s) to your saved connections?\n\n{ips}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.devices_selected.emit(selected)
        self.accept()

    def _clear_results(self):
        self._discovered = []
        self._checkboxes = []
        self.table.setRowCount(0)
        self.add_btn.setEnabled(False)
        self._update_select_buttons()
