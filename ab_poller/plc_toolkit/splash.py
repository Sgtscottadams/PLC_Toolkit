"""Startup splash — shown while the main window loads."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from plc_toolkit.resources import asset_path

_SPLASH_W = 480
_SPLASH_H = 280


def splash_pixmap(with_text: bool = True) -> QPixmap:
    """Continental-branded loading image (no external PNG required).

    ``with_text=False`` draws the logo only. This is used for the
    PyInstaller bootloader splash PNG, which is rendered at build time
    under the headless 'offscreen' Qt platform that has no fonts — baking
    text there produces tofu boxes. The runtime Qt splash (on Windows,
    where fonts exist) keeps the text.
    """
    pix = QPixmap(_SPLASH_W, _SPLASH_H)
    pix.fill(QColor("#0B162C"))

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)

    logo_path = asset_path("clr-logo.png")
    if logo_path is not None:
        logo = QPixmap(str(logo_path))
        if not logo.isNull():
            scaled = logo.scaledToHeight(72, Qt.SmoothTransformation)
            x = (_SPLASH_W - scaled.width()) // 2
            painter.drawPixmap(x, 56, scaled)

    if with_text:
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(0, 150, _SPLASH_W, 32, Qt.AlignHCenter, "PLC Toolkit")

        sub_font = QFont()
        sub_font.setPointSize(10)
        painter.setFont(sub_font)
        painter.setPen(QColor("#8FA4B8"))
        painter.drawText(
            0, 188, _SPLASH_W, 24, Qt.AlignHCenter, "Created by Scott Adams"
        )

    painter.end()
    return pix


def show_startup_splash(app: QApplication) -> QSplashScreen:
    """Display splash and pump events so it paints before heavy UI work."""
    splash = QSplashScreen(splash_pixmap(), Qt.WindowStaysOnTopHint)
    splash.show()
    app.processEvents()
    return splash
