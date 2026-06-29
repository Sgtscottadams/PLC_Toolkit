"""Stamped readings panel with in-box clipboard copy and toast feedback."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QLabel,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from plc_toolkit.ui.copy_toast import flash_copy_toast

# Continental blue → gold (matches brand header / CLR palette).
CLR_INDICATOR_GRADIENT = (
    "qlineargradient(x1:0, y1:0, x2:1, y2:1, "
    "stop:0 #1565C0, stop:0.55 #1976D2, stop:1 #B8860B)"
)


def clipboard_icon(size: int = 18) -> QIcon:
    """Simple clipboard pixmap — no extra assets or QtSvg dependency."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(Qt.GlobalColor.white, 1.4)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    pad = max(2, size // 8)
    clip_w = max(8, size - pad * 2)
    clip_h = max(10, int(size * 0.72))
    clip_x = (size - clip_w) // 2
    clip_y = pad + max(2, size // 6)
    p.drawRoundedRect(clip_x, clip_y, clip_w, clip_h, 2, 2)
    tab_w = max(6, clip_w - 4)
    tab_h = max(4, size // 5)
    tab_x = clip_x + (clip_w - tab_w) // 2
    tab_y = max(1, clip_y - tab_h + 1)
    p.drawRoundedRect(tab_x, tab_y, tab_w, tab_h, 1, 1)
    p.end()
    return QIcon(pix)


class StampReadingsPanel(QFrame):
    """Read-only stamp log with copy control in the bottom-right corner."""

    def __init__(self, max_height: int = 130, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("stampReadingsPanel")

        self.stamps_log = QTextEdit()
        self.stamps_log.setReadOnly(True)
        self.stamps_log.setMaximumHeight(max_height)
        self.stamps_log.setPlaceholderText("Stamped readings appear here…")
        stamp_font = QFont("Consolas", 9)
        if not stamp_font.exactMatch():
            stamp_font = QFont("Courier New", 9)
        self.stamps_log.setFont(stamp_font)
        self.stamps_log.setStyleSheet(
            "QTextEdit { padding-right: 34px; padding-bottom: 30px; }"
        )

        self._copy_btn = QToolButton(self)
        self._copy_btn.setObjectName("copyStampsBtn")
        self._copy_btn.setIcon(clipboard_icon())
        self._copy_btn.setToolTip("Copy all stamped readings to clipboard")
        self._copy_btn.setAutoRaise(True)
        self._copy_btn.setFixedSize(28, 28)
        self._copy_btn.clicked.connect(self._on_copy)

        title = QLabel("Stamped readings")
        title.setObjectName("hint")

        log_host = QWidget()
        grid = QGridLayout(log_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(self.stamps_log, 0, 0)
        grid.addWidget(self._copy_btn, 0, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        outer.addWidget(title)
        outer.addWidget(log_host)

    def _on_copy(self) -> None:
        text = self.stamps_log.toPlainText().strip()
        if not text:
            flash_copy_toast(self, self._copy_btn, "Nothing to copy")
            return
        clip = QApplication.clipboard()
        if clip is not None:
            clip.setText(text)
        flash_copy_toast(self, self._copy_btn, "Copied")
