"""Small inline toast label for copy confirmations."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QLabel, QWidget


def flash_copy_toast(parent: QWidget, anchor: QWidget, message: str = "Copied") -> None:
    """Show *message* briefly above *anchor* (no modal dialog)."""
    toast = getattr(parent, "_copy_toast_label", None)
    if toast is None:
        toast = QLabel(parent)
        toast.setObjectName("copyToast")
        toast.setAlignment(Qt.AlignCenter)
        parent._copy_toast_label = toast  # type: ignore[attr-defined]
    toast.setText(message)
    toast.adjustSize()
    margin = 6
    ax = anchor.x()
    ay = anchor.y()
    tx = max(margin, ax + anchor.width() - toast.width())
    ty = max(margin, ay - toast.height() - 4)
    toast.move(tx, ty)
    toast.show()
    toast.raise_()

    timer = getattr(parent, "_copy_toast_timer", None)
    if timer is None:
        timer = QTimer(parent)
        timer.setSingleShot(True)
        parent._copy_toast_timer = timer  # type: ignore[attr-defined]
    timer.stop()
    timer.timeout.connect(toast.hide)
    timer.start(1200)
