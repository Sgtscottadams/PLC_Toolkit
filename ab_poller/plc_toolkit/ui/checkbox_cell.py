"""Centered checkbox widget for table cells."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QWidget

from plc_toolkit.ui.stamp_panel import CLR_INDICATOR_GRADIENT

_TABLE_CHECKBOX_STYLE = f"""
QCheckBox#tableCheckbox {{
    background: transparent;
    spacing: 0px;
}}
QCheckBox#tableCheckbox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 3px;
}}
QCheckBox#tableCheckbox::indicator:unchecked {{
    background-color: #0F1E3D;
    border: 2px solid #B0BEC5;
}}
QCheckBox#tableCheckbox::indicator:unchecked:hover {{
    border-color: #E8ECF1;
}}
QCheckBox#tableCheckbox::indicator:checked {{
    background: {CLR_INDICATOR_GRADIENT};
    border: 2px solid #FFFFFF;
    image: none;
}}
QCheckBox#tableCheckbox::indicator:checked:hover {{
    border-color: #E8ECF1;
}}
"""


class CenteredCheckBoxCell(QWidget):
    """A checkbox centered inside a table cell."""

    toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent;")
        self._silent = False
        self._box = QCheckBox()
        self._box.setObjectName("tableCheckbox")
        self._box.setStyleSheet(_TABLE_CHECKBOX_STYLE)
        self._box.setTristate(False)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._box)
        self._box.stateChanged.connect(self._on_state_changed)

    def _on_state_changed(self, state: int) -> None:
        if self._silent:
            return
        self.toggled.emit(self._box.isChecked())

    def is_checked(self) -> bool:
        return self._box.isChecked()

    def set_checked(self, checked: bool) -> None:
        if self._box.isChecked() == checked:
            return
        self._silent = True
        try:
            self._box.setChecked(checked)
        finally:
            self._silent = False
