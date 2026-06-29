"""Settings dialog — wireframe core sections (09-settings.html)."""

from __future__ import annotations

from dataclasses import asdict

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from plc_toolkit import style as app_style
from plc_toolkit.settings_store import AppSettings, app_data_dir, portable_mode


class SettingsDialog(QDialog):
    """Modal settings editor. Emits settings_saved when the user clicks OK."""

    settings_saved = Signal(object)  # AppSettings

    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setObjectName("settingsDialog")
        self.setStyleSheet(app_style.STYLESHEET)
        self.resize(640, 520)
        self._settings = settings

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        lay = QVBoxLayout(body)

        lay.addWidget(self._build_connection_group())
        lay.addWidget(self._build_polling_group())
        lay.addWidget(self._build_storage_group())
        lay.addWidget(self._build_export_group())
        lay.addStretch()
        scroll.setWidget(body)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        outer = QVBoxLayout(self)
        outer.addWidget(scroll)
        outer.addWidget(buttons)

        self._load_from_settings()

    def _build_connection_group(self) -> QGroupBox:
        g = QGroupBox("Connection")
        form = QFormLayout(g)

        self.timeout_spin = QDoubleSpinBox()
        self.timeout_spin.setRange(1, 60)
        self.timeout_spin.setSuffix(" s")
        form.addRow("Default connection timeout", self.timeout_spin)

        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(0, 10)
        form.addRow("Connect retries", self.retries_spin)

        self.retry_delay_spin = QSpinBox()
        self.retry_delay_spin.setRange(0, 10000)
        self.retry_delay_spin.setSingleStep(100)
        self.retry_delay_spin.setSuffix(" ms")
        form.addRow("Retry delay", self.retry_delay_spin)

        self.auto_reconnect_cb = QCheckBox("Auto-reconnect on dropped session")
        form.addRow(self.auto_reconnect_cb)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        form.addRow("Default port", self.port_spin)

        self.verify_ip_cb = QCheckBox(
            "Verify IP is reachable before opening CIP session"
        )
        form.addRow(self.verify_ip_cb)

        form.addRow(QLabel("<b>Discovery defaults</b>"))
        self.disc_network = QLineEdit()
        self.disc_network.setPlaceholderText("(auto from interface)")
        form.addRow("Default network", self.disc_network)

        self.disc_cidr = QComboBox()
        for c in ("/16", "/20", "/24", "/25", "/26", "/27", "/28"):
            self.disc_cidr.addItem(c)
        form.addRow("Default CIDR", self.disc_cidr)

        return g

    def _build_polling_group(self) -> QGroupBox:
        g = QGroupBox("Polling & display")
        form = QFormLayout(g)

        self.poll_combo = QComboBox()
        for label in ("5 s", "15 s", "30 s", "1 min", "5 min"):
            self.poll_combo.addItem(label)
        form.addRow("Default poll rate", self.poll_combo)

        sym = QCheckBox("Use symbolic addressing (always on with pylogix)")
        sym.setChecked(True)
        sym.setEnabled(False)
        form.addRow(sym)

        self.bool_combo = QComboBox()
        self.bool_combo.addItems(["0 / 1", "FALSE / TRUE", "Off / On"])
        form.addRow("BOOL display", self.bool_combo)

        self.trend_spin = QSpinBox()
        self.trend_spin.setRange(10, 8640)
        self.trend_spin.setToolTip(
            "Samples kept per tag on the Monitor tab (sparkline + export). "
            "At a 5 s poll interval, 720 ≈ 1 hour, 8640 ≈ 12 hours."
        )
        form.addRow("Monitor history depth (samples)", self.trend_spin)

        return g

    def _build_storage_group(self) -> QGroupBox:
        g = QGroupBox("Storage")
        form = QFormLayout(g)

        self.db_path = QLineEdit()
        db_row = QHBoxLayout()
        db_row.addWidget(self.db_path, 1)
        db_browse = QPushButton("Browse…")
        db_browse.clicked.connect(lambda: self._browse_dir(self.db_path, file=True))
        db_row.addWidget(db_browse)
        form.addRow("Database path", db_row)

        self.scans_path = QLineEdit()
        scans_row = QHBoxLayout()
        scans_row.addWidget(self.scans_path, 1)
        scans_browse = QPushButton("Browse…")
        scans_browse.clicked.connect(lambda: self._browse_dir(self.scans_path))
        scans_row.addWidget(scans_browse)
        form.addRow("Scan archives", scans_row)

        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(1, 3650)
        form.addRow("Retain history (days)", self.retention_spin)

        self.auto_prune_cb = QCheckBox(
            "Auto-prune scans older than retention window"
        )
        form.addRow(self.auto_prune_cb)

        encrypt = QCheckBox(
            "Encrypt local database (SQLCipher) — planned for v2.1"
        )
        encrypt.setEnabled(False)
        form.addRow(encrypt)

        return g

    def _build_export_group(self) -> QGroupBox:
        g = QGroupBox("Export")
        form = QFormLayout(g)

        self.export_path = QLineEdit()
        exp_row = QHBoxLayout()
        exp_row.addWidget(self.export_path, 1)
        exp_browse = QPushButton("Browse…")
        exp_browse.clicked.connect(lambda: self._browse_dir(self.export_path))
        exp_row.addWidget(exp_browse)
        form.addRow("Default export folder", exp_row)

        self.fname_template = QLineEdit()
        form.addRow("Filename template", self.fname_template)
        hint = QLabel(
            "Tokens: {nickname}, {ip}, {slot}, {YYYY-MM-DD}, {HHmm}"
        )
        hint.setObjectName("hint")
        form.addRow(hint)

        return g

    def _browse_dir(self, target: QLineEdit, file: bool = False) -> None:
        if file:
            path, _ = QFileDialog.getSaveFileName(
                self, "Database path", str(app_data_dir()), "SQLite (*.db)"
            )
        else:
            path = QFileDialog.getExistingDirectory(
                self, "Choose folder", str(app_data_dir())
            )
        if path:
            target.setText(path)

    def _load_from_settings(self) -> None:
        s = self._settings
        self.timeout_spin.setValue(s.connection_timeout_s)
        self.retries_spin.setValue(s.connect_retries)
        self.retry_delay_spin.setValue(s.retry_delay_ms)
        self.auto_reconnect_cb.setChecked(s.auto_reconnect)
        self.port_spin.setValue(s.default_port)
        self.verify_ip_cb.setChecked(s.verify_ip_before_cip)
        self.disc_network.setText(s.default_discover_network)
        idx = self.disc_cidr.findText(s.default_discover_cidr)
        if idx >= 0:
            self.disc_cidr.setCurrentIndex(idx)
        poll_map = {5: "5 s", 15: "15 s", 30: "30 s", 60: "1 min", 300: "5 min"}
        poll_label = poll_map.get(int(s.default_poll_rate_s), "5 s")
        pidx = self.poll_combo.findText(poll_label)
        if pidx >= 0:
            self.poll_combo.setCurrentIndex(pidx)
        bidx = self.bool_combo.findText(s.bool_display)
        if bidx >= 0:
            self.bool_combo.setCurrentIndex(bidx)
        self.trend_spin.setValue(s.trend_window_samples)
        self.db_path.setText(str(s.resolved_db_path()))
        self.scans_path.setText(str(s.resolved_scans_dir()))
        self.retention_spin.setValue(s.retention_days)
        self.auto_prune_cb.setChecked(s.auto_prune_scans)
        self.export_path.setText(str(s.resolved_export_dir()))
        self.fname_template.setText(s.filename_template)

    def _persist_path(self, text: str, default: Path) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        try:
            chosen = Path(text).expanduser().resolve()
            default_resolved = default.resolve()
        except OSError:
            return ""
        if portable_mode():
            from plc_toolkit.settings_store import path_under_install

            if not path_under_install(chosen):
                return ""
        if chosen == default_resolved:
            return ""
        return str(chosen)

    def _on_accept(self) -> None:
        poll_labels = {"5 s": 5, "15 s": 15, "30 s": 30, "1 min": 60, "5 min": 300}
        draft = AppSettings(
            connection_timeout_s=self.timeout_spin.value(),
            connect_retries=self.retries_spin.value(),
            retry_delay_ms=self.retry_delay_spin.value(),
            auto_reconnect=self.auto_reconnect_cb.isChecked(),
            default_port=self.port_spin.value(),
            verify_ip_before_cip=self.verify_ip_cb.isChecked(),
            default_discover_network=self.disc_network.text().strip(),
            default_discover_cidr=self.disc_cidr.currentText(),
            default_poll_rate_s=float(
                poll_labels.get(self.poll_combo.currentText(), 5)
            ),
            bool_display=self.bool_combo.currentText(),
            trend_window_samples=self.trend_spin.value(),
            retention_days=self.retention_spin.value(),
            auto_prune_scans=self.auto_prune_cb.isChecked(),
            filename_template=self.fname_template.text().strip(),
            theme=self._settings.theme,
        )
        s = AppSettings(
            **{
                **asdict(draft),
                "db_path": self._persist_path(
                    self.db_path.text(), draft.resolved_db_path()
                ),
                "scans_dir": self._persist_path(
                    self.scans_path.text(), draft.resolved_scans_dir()
                ),
                "export_dir": self._persist_path(
                    self.export_path.text(), draft.resolved_export_dir()
                ),
            }
        )
        s.save()
        self._settings = s
        self.settings_saved.emit(s)
        self.accept()
