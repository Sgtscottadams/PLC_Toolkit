"""Connection Manager — the landing page.

Lists saved PLC connections from the SQLite DB. The user can:
    - Click a row to connect to that PLC (emits `plc_selected(PlcConnection)`).
    - Click '+ Connect to a new PLC' to open the NewConnectionDialog.
    - Click 'Discover on subnet' to run a UDP broadcast and pick a
      discovered PLC to add to the saved list.
    - Click 'Remove selected' to delete a saved connection (with
      confirmation).

This is the wireframe equivalent of mockups/01-connection-manager.html
from the design phase.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

import plck
from plck.comms import PLCClient
from plck.db import DatabaseManager
from plck.device_filter import is_tag_readable_controller, unsupported_device_message
from plck.errors import PlcError
from plck.models import PlcConnection

from plc_toolkit.ui.brand_header import BrandHeader
from plc_toolkit.ui.new_connection_dialog import NewConnectionDialog
from plc_toolkit.ui.subnet_scan_dialog import SubnetScanDialog
from plc_toolkit.settings_store import AppSettings
from plc_toolkit.workers import SubnetDiscoveryWorker


def _format_last_scan(iso_ts: Optional[str]) -> str:
    """Human-readable relative time for the Last scan column."""
    if not iso_ts or not str(iso_ts).strip():
        return "Never"
    try:
        raw = str(iso_ts).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        secs = int((datetime.now(timezone.utc) - dt).total_seconds())
        if secs < 60:
            return "Just now"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"
    except (ValueError, TypeError):
        return str(iso_ts)


class ConnectionView(QWidget):
    """The Connection Manager landing page."""

    plc_selected = Signal(object)  # PlcConnection
    settings_requested = Signal()

    _COL_NICKNAME = 0
    _COL_DEVICE = 1
    _COL_IP = 2
    _COL_SLOT = 3
    _COL_PORT = 4
    _COL_REVISION = 5
    _COL_LAST_SCAN = 6
    _COL_CONNECT = 7

    def __init__(self, db: DatabaseManager, settings: Optional[AppSettings] = None) -> None:
        super().__init__()
        self.db = db
        self.settings = settings or AppSettings.load()
        self._subnet_worker: Optional[SubnetDiscoveryWorker] = None
        self._discovered: list[dict] = []
        self._populating_table = False

        # -- Brand top bar (wireframe topbar-left) -----------------------
        topbar = QHBoxLayout()
        topbar.addWidget(BrandHeader(), 1)
        self.settings_btn = QPushButton("⚙ Settings")
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        topbar.addWidget(self.settings_btn)

        # -- Section title -----------------------------------------------
        title = QLabel("Saved connections")
        title.setObjectName("pageTitle")

        self._cached_plcs: list[PlcConnection] = []
        self._sort_column = self._COL_IP
        self._sort_ascending = True

        # -- Table -------------------------------------------------------
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Nickname", "Device ID", "IP", "Slot", "Port", "Revision",
            "Last scan", "Connect",
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(self._COL_NICKNAME, QHeaderView.Stretch)
        h.setSectionResizeMode(self._COL_DEVICE, QHeaderView.ResizeToContents)
        for c in range(self._COL_IP, self._COL_LAST_SCAN + 1):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self._COL_CONNECT, QHeaderView.ResizeToContents)
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_header_clicked)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemChanged.connect(self._on_nickname_edited)

        # -- Buttons -----------------------------------------------------
        self.add_btn = QPushButton("+ Connect to a new PLC")
        self.add_btn.clicked.connect(self._on_add)
        self.discover_btn = QPushButton("Discover on subnet")
        self.discover_btn.clicked.connect(self._on_discover)
        self.remove_btn = QPushButton("Remove selected")
        self.remove_btn.clicked.connect(self._on_remove)
        self.remove_btn.setEnabled(False)
        self.connect_btn = QPushButton("Connect to selected")
        self.connect_btn.setDefault(True)
        self.connect_btn.clicked.connect(self._on_connect)
        self.connect_btn.setEnabled(False)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.discover_btn)
        btn_row.addWidget(self.remove_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.connect_btn)

        # -- Status row --------------------------------------------------
        self.status_label = QLabel("Ready.")
        self.status_label.setObjectName("statusLabel")

        outer = QVBoxLayout(self)
        outer.addLayout(topbar)
        outer.addWidget(title)
        outer.addWidget(self.table)
        outer.addLayout(btn_row)
        outer.addWidget(self.status_label)

        self.refresh()

    # -- Refresh / data ---------------------------------------------------

    def refresh(self) -> None:
        self._cached_plcs = self.db.list_plcs()
        self._repopulate_table()

    def _sort_key(self, plc: PlcConnection):
        col = self._sort_column
        if col == self._COL_NICKNAME:
            return (plc.nickname or "").lower()
        if col == self._COL_DEVICE:
            return (plc.device_display() or "").lower()
        if col == self._COL_IP:
            return plc.ip or ""
        if col == self._COL_SLOT:
            return int(plc.slot)
        if col == self._COL_PORT:
            return int(plc.port)
        if col == self._COL_REVISION:
            return (plc.revision or "").lower()
        if col == self._COL_LAST_SCAN:
            return plc.last_scan or ""
        return ""

    def _on_header_clicked(self, logical_index: int) -> None:
        if logical_index == self._COL_CONNECT or not self._cached_plcs:
            return
        if logical_index == self._sort_column:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_column = logical_index
            self._sort_ascending = True
        self._repopulate_table()

    def _repopulate_table(self) -> None:
        plcs = sorted(
            self._cached_plcs,
            key=self._sort_key,
            reverse=not self._sort_ascending,
        )
        self._populating_table = True
        try:
            self.table.setRowCount(0)
            if not plcs:
                self.table.setRowCount(1)
                cell = QTableWidgetItem(
                    "No saved connections yet. Click + Connect to a new PLC to add one, "
                    "or Discover on subnet to find PLCs on your network."
                )
                cell.setFlags(Qt.NoItemFlags)
                self.table.setItem(0, 0, cell)
                self.table.setSpan(0, 0, 1, 8)
                return
            editable = Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable
            readonly = Qt.ItemIsSelectable | Qt.ItemIsEnabled
            for r, plc in enumerate(plcs):
                self.table.insertRow(r)
                nick_item = QTableWidgetItem(plc.nickname or "")
                nick_item.setFlags(editable)
                nick_item.setData(Qt.UserRole, plc)
                self.table.setItem(r, self._COL_NICKNAME, nick_item)
                dev_item = QTableWidgetItem(plc.device_display() or "—")
                dev_item.setToolTip(
                    plc.device_label() if plc.device_label() != plc.ip else ""
                )
                dev_item.setFlags(readonly)
                self.table.setItem(r, self._COL_DEVICE, dev_item)
                self.table.setItem(r, self._COL_IP, QTableWidgetItem(plc.ip))
                self.table.setItem(r, self._COL_SLOT, QTableWidgetItem(str(plc.slot)))
                self.table.setItem(r, self._COL_PORT, QTableWidgetItem(str(plc.port)))
                prod_item = QTableWidgetItem(plc.revision or "—")
                prod_item.setFlags(readonly)
                self.table.setItem(r, self._COL_REVISION, prod_item)
                self.table.setItem(
                    r, self._COL_LAST_SCAN,
                    QTableWidgetItem(_format_last_scan(plc.last_scan)),
                )
                for c in range(self._COL_IP, self._COL_LAST_SCAN + 1):
                    item = self.table.item(r, c)
                    if item is not None:
                        item.setFlags(readonly)
                connect_btn = QPushButton("Connect")
                connect_btn.setObjectName("rowConnectBtn")
                connect_btn.clicked.connect(
                    lambda *_, row=r: self._connect_row(row)
                )
                self.table.setCellWidget(r, self._COL_CONNECT, connect_btn)
        finally:
            self._populating_table = False

    def selected_plc(self) -> Optional[PlcConnection]:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._plc_at_row(rows[0].row())

    def _plc_at_row(self, row: int) -> Optional[PlcConnection]:
        item = self.table.item(row, self._COL_NICKNAME)
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _remove_saved_plc(self, plc: PlcConnection) -> bool:
        """Delete a saved connection without a confirmation dialog."""
        try:
            self.db.remove_plc(plc.ip, plc.slot)
        except Exception as e:
            QMessageBox.critical(
                self, "Database error",
                f"Could not remove connection: {e}",
            )
            return False
        self.status_label.setText(f"Removed '{plc.display_label()}'.")
        self.refresh()
        return True

    def _unsupported_device_dialog(self, plc: PlcConnection) -> str:
        """Warn when Connect targets a non-Logix device.

        Returns ``"remove"`` if the operator chose **Remove from list**,
        otherwise ``"dismiss"``.
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Not a tag-readable PLC")
        box.setText(unsupported_device_message(plc.product_name))
        remove_btn = box.addButton(
            "Remove from list", QMessageBox.DestructiveRole,
        )
        box.addButton(QMessageBox.Ok)
        box.setDefaultButton(box.button(QMessageBox.Ok))
        box.exec()
        if box.clickedButton() is remove_btn:
            return "remove"
        return "dismiss"

    def _connect_row(self, row: int) -> None:
        plc = self._plc_at_row(row)
        if plc is None:
            return
        if plc.product_name and not is_tag_readable_controller(
            plc.product_name, plc.vendor,
        ):
            if self._unsupported_device_dialog(plc) == "remove":
                self._remove_saved_plc(plc)
            return
        self.plc_selected.emit(plc)

    def _on_nickname_edited(self, item: QTableWidgetItem) -> None:
        if self._populating_table or item.column() != self._COL_NICKNAME:
            return
        plc = item.data(Qt.UserRole)
        if plc is None:
            return
        nickname = item.text().strip()
        try:
            self.db.update_plc_nickname(plc.ip, plc.slot, nickname)
        except Exception as e:
            QMessageBox.critical(
                self, "Database error",
                f"Could not save nickname: {e}",
            )
            self.refresh()
            return
        plc.nickname = nickname
        item.setData(Qt.UserRole, plc)
        self.status_label.setText(
            f"Saved nickname for {plc.display_label()} ({plc.ip})."
        )

    def _on_cell_double_clicked(self, row: int, column: int) -> None:
        if column == self._COL_NICKNAME:
            item = self.table.item(row, self._COL_NICKNAME)
            if item is not None:
                self.table.setCurrentCell(row, self._COL_NICKNAME)
                self.table.editItem(item)
            return
        if column == self._COL_CONNECT:
            return
        self._connect_row(row)

    # -- Slots ------------------------------------------------------------

    def _on_selection_changed(self) -> None:
        has = self.selected_plc() is not None
        self.connect_btn.setEnabled(has)
        self.remove_btn.setEnabled(has)

    def _on_connect(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self._connect_row(rows[0].row())

    def _on_add(self) -> None:
        dlg = NewConnectionDialog(self)
        dlg.connection_accepted.connect(self._on_new_connection_accepted)
        dlg.exec()

    def _on_new_connection_accepted(self, plc: PlcConnection) -> None:
        try:
            self.db.upsert_plc(plc)
        except Exception as e:
            QMessageBox.critical(
                self, "Database error",
                f"Could not save connection: {e}",
            )
            return
        self.refresh()
        label = plc.display_label()
        self.status_label.setText(f"Saved '{label}' ({plc.ip}).")

    def _on_remove(self) -> None:
        plc = self.selected_plc()
        if plc is None:
            return
        confirm = QMessageBox.question(
            self,
            "Remove connection?",
            f"Remove '{plc.display_label()}' ({plc.ip}) from saved connections?\n\n"
            f"This will also delete {len(self.db.list_scans(self.db.upsert_plc(plc)))} "
            f"scan history rows for this PLC.\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self.db.remove_plc(plc.ip, plc.slot)
        except Exception as e:
            QMessageBox.critical(
                self, "Database error",
                f"Could not remove connection: {e}",
            )
            return
        self.status_label.setText(f"Removed '{plc.display_label()}'.")
        self.refresh()

    def apply_settings(self, settings: AppSettings) -> None:
        self.settings = settings

    def _on_discover(self) -> None:
        """Open the subnet discovery dialog."""
        dlg = SubnetScanDialog(self)
        net = self.settings.default_discover_network.strip()
        if net:
            cidr = self.settings.default_discover_cidr
            dlg.subnet_input.setText(
                net if "/" in net else f"{net}{cidr}"
            )
        dlg.devices_selected.connect(self._on_devices_selected)
        dlg.exec()

    def _on_devices_selected(self, devices: list) -> None:
        """Batch-insert discovered PLCs into the database."""
        from plck.models import PlcConnection
        added = 0
        for d in devices:
            product_name = (d.get("product_name") or "").strip()
            revision = (d.get("revision") or "").strip() or None
            plc = PlcConnection(
                nickname="",
                device_id=product_name or None,
                ip=d["ip"],
                product_name=product_name or None,
                revision=revision,
            )
            self.db.upsert_plc(plc)
            added += 1
        self.refresh()
        self.status_label.setText(
            f"Added {added} PLC(s). Click Connect or double-click a row to open."
        )
