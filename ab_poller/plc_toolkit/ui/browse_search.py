"""Browse tab search field with a visible clear (×) button."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QPushButton


class BrowseSearchBox(QFrame):
    """Search field with a visible clear button.

    QLineEdit trailing ``QAction`` buttons are often invisible on Windows;
    a sibling push button stays reliably themed and clickable.
    """

    textChanged = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("browseSearchFrame")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 4, 4)
        lay.setSpacing(4)

        self.input = QLineEdit()
        self.input.setObjectName("browseSearchInput")
        self.input.setFrame(False)
        self.input.textChanged.connect(self.textChanged.emit)
        self.input.textChanged.connect(self._sync_clear_visible)

        self.clear_btn = QPushButton("×")
        self.clear_btn.setObjectName("searchClearBtn")
        self.clear_btn.setFixedSize(26, 22)
        self.clear_btn.setToolTip("Clear search")
        self.clear_btn.setVisible(False)
        self.clear_btn.clicked.connect(self.input.clear)

        lay.addWidget(self.input, 1)
        lay.addWidget(self.clear_btn)

    def _sync_clear_visible(self, text: str) -> None:
        self.clear_btn.setVisible(bool((text or "").strip()))
