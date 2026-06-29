"""plc_toolkit.app — QApplication entry point and MainWindow.

Run with:
    python -m plc_toolkit
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import pylogix
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QStackedWidget, QStatusBar,
)

import plck
from plck.db import DatabaseManager
from plck.models import PlcConnection

from plc_toolkit import style as _style
from plc_toolkit.settings_store import AppSettings, ensure_portable_layout
from plc_toolkit.splash import show_startup_splash
from plc_toolkit.ui import ConnectionView, WorkspaceView
from plc_toolkit.ui.help_dialog import HelpDialog
from plc_toolkit.ui.settings_dialog import SettingsDialog


def _default_outdir(settings: AppSettings) -> Path:
    """Export directory from settings; override via PLC_TOOLKIT_OUTDIR."""
    override = os.environ.get("PLC_TOOLKIT_OUTDIR")
    if override:
        outdir = Path(override)
    else:
        outdir = settings.resolved_export_dir()
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


def _default_db_path(settings: AppSettings) -> Optional[Path]:
    override = os.environ.get("PLC_TOOLKIT_DB")
    if override:
        return Path(override)
    return settings.resolved_db_path()


class MainWindow(QMainWindow):
    """The top-level window. Holds the connection view and the workspace
    view; flips between them with a QStackedWidget."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PLC Toolkit")
        self.resize(1280, 800)

        self.settings = AppSettings.load()
        db_path = _default_db_path(self.settings)
        self.db = DatabaseManager(path=str(db_path) if db_path else None)
        self.outdir = _default_outdir(self.settings)

        self.connection_view = ConnectionView(self.db, self.settings)
        self.workspace_view = WorkspaceView(
            self.db, self.outdir, settings=self.settings
        )
        self.workspace_view.disconnected.connect(self._on_disconnected)
        self.connection_view.plc_selected.connect(self._on_plc_selected)
        self.connection_view.settings_requested.connect(self._on_settings)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.connection_view)  # 0
        self.stack.addWidget(self.workspace_view)    # 1
        self.setCentralWidget(self.stack)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._refresh_status_bar()

        self._build_menu()

    def _refresh_status_bar(self) -> None:
        self.status_bar.showMessage(
            f"DB: {self.db.path}    Outdir: {self.outdir}"
        )

    def _build_menu(self) -> None:
        m_file = self.menuBar().addMenu("&File")
        a_refresh = QAction("&Refresh connections", self)
        a_refresh.setShortcut(QKeySequence("F5"))
        a_refresh.triggered.connect(self.connection_view.refresh)
        m_file.addAction(a_refresh)
        m_file.addSeparator()
        a_settings = QAction("&Settings…", self)
        a_settings.setShortcut(QKeySequence("Ctrl+,"))
        a_settings.triggered.connect(self._on_settings)
        m_file.addAction(a_settings)
        m_file.addSeparator()
        a_quit = QAction("&Quit", self)
        a_quit.setShortcut(QKeySequence("Ctrl+Q"))
        a_quit.triggered.connect(self.close)
        m_file.addAction(a_quit)

        m_view = self.menuBar().addMenu("&View")
        a_conn = QAction("&Connections", self)
        a_conn.setShortcut(QKeySequence("Ctrl+1"))
        a_conn.triggered.connect(self._show_connection_view)
        m_view.addAction(a_conn)

        m_help = self.menuBar().addMenu("&Help")
        a_help = QAction("&Help topics…", self)
        a_help.setShortcut(QKeySequence("F1"))
        a_help.triggered.connect(self._on_help)
        m_help.addAction(a_help)
        a_about = QAction("&About PLC Toolkit", self)
        a_about.triggered.connect(self._on_about)
        m_help.addAction(a_about)

    def _on_settings(self) -> None:
        dlg = SettingsDialog(self.settings, self)
        dlg.settings_saved.connect(self._apply_settings)
        dlg.exec()

    def _apply_settings(self, settings: AppSettings) -> None:
        self.settings = settings
        self.outdir = _default_outdir(settings)
        self.workspace_view.apply_settings(settings)
        self.connection_view.apply_settings(settings)
        self._refresh_status_bar()

    def _on_help(self) -> None:
        HelpDialog(self).exec()

    def _on_plc_selected(self, plc: PlcConnection) -> None:
        self.workspace_view.connect_to(plc)
        self.stack.setCurrentIndex(1)

    def _on_disconnected(self) -> None:
        self.workspace_view.shutdown()
        self.connection_view.refresh()
        self.stack.setCurrentIndex(0)

    def _show_connection_view(self) -> None:
        self.stack.setCurrentIndex(0)

    def _on_about(self) -> None:
        ver = getattr(pylogix, "__version__", "unknown")
        QMessageBox.about(
            self, "About PLC Toolkit",
            "<h3>PLC Toolkit v2.0</h3>"
            "<p>Allen-Bradley / EtherNet/IP tag discovery, export, and live "
            "monitoring.</p>"
            f"<p>Built with PySide6 and pylogix {ver}.</p>"
            "<p><b>READ-ONLY</b> — no writes to the PLC.</p>"
            "<p>Created by Scott Adams.</p>"
        )

    def closeEvent(self, event) -> None:
        self.workspace_view.shutdown()
        self.db.close()
        super().closeEvent(event)


def _close_pyi_splash() -> None:
    """Dismiss the PyInstaller bootloader splash, if present.

    In a onefile build the bootloader shows a splash during unpack. It
    stays on top for the whole session unless the app closes it — which is
    why it appeared 'stuck'. Only exists in the frozen build.
    """
    try:
        import pyi_splash  # type: ignore
        pyi_splash.close()
    except Exception:
        pass


def main() -> int:
    ensure_portable_layout()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("PLC Toolkit")
    app.setOrganizationName("Continental Resources")
    app.setStyleSheet(_style.STYLESHEET)
    splash = show_startup_splash(app)
    # Hand off from the bootloader splash to our own Qt splash.
    _close_pyi_splash()
    w = MainWindow()
    w.show()
    splash.finish(w)
    splash.deleteLater()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
