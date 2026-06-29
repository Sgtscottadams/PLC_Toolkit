"""Top bar brand row — Continental logo + PLC Toolkit title."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


from plc_toolkit.resources import asset_path


def _logo_path():
    """Return clr-logo.png if bundled or present in the repo."""
    return asset_path("clr-logo.png")


class BrandHeader(QWidget):
    """Wireframe topbar-left: logo + 'PLC Toolkit' product title."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("brandHeader")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        logo_path = _logo_path()
        if logo_path is not None:
            logo = QLabel()
            logo.setObjectName("brandLogo")
            pix = QPixmap(str(logo_path))
            if not pix.isNull():
                logo.setPixmap(
                    pix.scaledToHeight(32, Qt.SmoothTransformation)
                )
                lay.addWidget(logo)

        title = QLabel("PLC Toolkit")
        title.setObjectName("brandTitle")
        lay.addWidget(title)
        lay.addStretch()
