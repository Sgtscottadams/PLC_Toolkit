"""plc_toolkit style — Continental Resources brand dark theme.

Navy-blue-gold palette matching the CLR wireframes. Dark-mode
readability preserved for control-room 24/7 use.

Token map:
    Backgrounds:  #0B162C (canvas) -> #0F1E3D (surface) -> #162A4A (elevated) -> #1D3559 (hover)
    Text:         #E8ECF1 (primary), #8FA4B8 (secondary), #5A6E82 (disabled)
    Accent:       #1565C0 (CLR blue — buttons, selections, focus), #1976D2 (hover), #0D47A1 (pressed)
    Gold:         #B8860B (CLR gold — Monitor tab indicator, warnings only)
    Status:       #43A047 (OK/running), #B8860B (warning), #E53935 (alarm), #8FA4B8 (unknown)
"""

STYLESHEET = """
QMainWindow {
    background: #0B162C;
    color: #E8ECF1;
}

QFrame {
    background: transparent;
}

QLabel {
    color: #E8ECF1;
}

QLabel#pageTitle {
    font-size: 16px;
    font-weight: 700;
    color: #FFFFFF;
    padding: 4px 0;
}

QLabel#statusLabel, QLabel#statusBar, QLabel#hint {
    color: #8FA4B8;
    font-size: 11px;
}

QPushButton {
    background: #0F1E3D;
    color: #E8ECF1;
    border: 1px solid #2A4060;
    padding: 6px 14px;
    border-radius: 3px;
    min-height: 18px;
}
QPushButton:hover {
    background: #1D3559;
    border-color: #1565C0;
}
QPushButton:pressed {
    background: #0B162C;
}
QPushButton:disabled {
    color: #5A6E82;
    background: #0D1A33;
    border-color: #1A3050;
}

QCheckBox, QRadioButton {
    color: #E8ECF1;
    spacing: 6px;
    background: transparent;
}
QCheckBox:disabled, QRadioButton:disabled {
    color: #5A6E82;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #2A4060;
    background: #0F1E3D;
}
QCheckBox::indicator { border-radius: 2px; }
QRadioButton::indicator { border-radius: 8px; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #1565C0, stop:0.55 #1976D2, stop:1 #B8860B);
    border-color: #FFFFFF;
}
QCheckBox::indicator:unchecked, QRadioButton::indicator:unchecked {
    background: #0F1E3D;
    border: 2px solid #8FA4B8;
}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: #E8ECF1;
}

QTableWidget::item:selected {
    background-color: #1D3559;
    color: #E8ECF1;
}
QTableWidget::item:selected:active {
    background-color: #1565C0;
    color: #FFFFFF;
}

QToolTip {
    background: #162A4A;
    color: #E8ECF1;
    border: 1px solid #2A4060;
}

QWidget#brandHeader {
    background: transparent;
}
QLabel#brandTitle {
    font-size: 18px;
    font-weight: 700;
    color: #FFFFFF;
    letter-spacing: 0.3px;
}

QToolButton#copyStampsBtn {
    background: rgba(15, 30, 61, 0.85);
    border: 1px solid #2A4060;
    border-radius: 3px;
    padding: 2px;
}
QToolButton#copyStampsBtn:hover {
    background: rgba(29, 53, 89, 0.95);
    border-color: #1565C0;
}

QLabel#copyToast {
    background: #162A4A;
    color: #E8ECF1;
    border: 1px solid #1565C0;
    border-radius: 3px;
    padding: 4px 10px;
    font-size: 11px;
}

QGroupBox {
    color: #E8ECF1;
    border: 1px solid #2A4060;
    border-radius: 3px;
    margin-top: 14px;
    padding: 12px 8px 8px 8px;
    background: #0F1E3D;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 6px;
    color: #FFFFFF;
    font-weight: 600;
}

QScrollArea {
    background: #0F1E3D;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background: #0F1E3D;
}

QDialogButtonBox {
    background: transparent;
}

QFrame#browseSearchFrame {
    background: #0F1E3D;
    border: 1px solid #2A4060;
    border-radius: 2px;
}
QFrame#browseSearchFrame QLineEdit#browseSearchInput {
    background: transparent;
    border: none;
    padding: 2px 0;
}
QPushButton#searchClearBtn {
    background: #1565C0;
    color: #FFFFFF;
    font-size: 14px;
    font-weight: 700;
    border: none;
    border-radius: 2px;
    padding: 0;
    min-width: 24px;
    min-height: 20px;
}
QPushButton#searchClearBtn:hover {
    background: #1976D2;
}
QPushButton#searchClearBtn:disabled {
    background: #2A4060;
    color: #888888;
}

QLineEdit#browseSearch {
    padding-right: 28px;
}
QLineEdit#browseSearch QToolButton,
QLineEdit#browseSearch QAbstractButton {
    border: none;
    background: #1D3559;
    color: #FFFFFF;
    font-size: 15px;
    font-weight: 700;
    padding: 0 7px;
    min-width: 22px;
    min-height: 18px;
    border-radius: 2px;
    margin-right: 2px;
}
QLineEdit#browseSearch QToolButton:hover,
QLineEdit#browseSearch QAbstractButton:hover {
    background: #1565C0;
    color: #FFFFFF;
}

QTableWidget QPushButton#rowConnectBtn {
    padding: 4px 10px;
    min-height: 16px;
}

QComboBox QAbstractItemView {
    background: #0F1E3D;
    color: #E8ECF1;
    border: 1px solid #2A4060;
    selection-background-color: #1565C0;
    selection-color: #FFFFFF;
}

QPushButton#destructiveBtn {
    color: #E53935;
    border-color: #6A3A36;
}
QPushButton#destructiveBtn:hover {
    background: #3A2624;
    border-color: #E53935;
}

QTableWidget, QTreeWidget, QListWidget, QTextEdit, QLineEdit, QSpinBox, QComboBox {
    background: #0F1E3D;
    color: #E8ECF1;
    border: 1px solid #2A4060;
    gridline-color: #1A3050;
    selection-background-color: #1565C0;
    selection-color: #FFFFFF;
    alternate-background-color: #111F3F;
}
QHeaderView::section {
    background: #0B162C;
    color: #FFFFFF;
    padding: 4px 8px;
    border: 0;
    border-right: 1px solid #1A3050;
    border-bottom: 1px solid #1A3050;
    font-weight: 600;
}
QLineEdit, QSpinBox, QComboBox {
    padding: 4px 6px;
    border-radius: 2px;
    selection-background-color: #1565C0;
}

QMenuBar {
    background: #0A1426;
    color: #E8ECF1;
    border-bottom: 1px solid #1A3050;
}
QMenuBar::item:selected {
    background: #1D3559;
}
QMenu {
    background: #0F1E3D;
    color: #E8ECF1;
    border: 1px solid #2A4060;
}
QMenu::item:selected {
    background: #1565C0;
}

QTabWidget::pane {
    border: 1px solid #2A4060;
    background: #0B162C;
    top: -1px;
}
QTabBar::tab {
    background: #0A1426;
    color: #8FA4B8;
    padding: 6px 18px;
    border: 1px solid #2A4060;
    border-bottom: none;
    margin-right: 1px;
    min-width: 80px;
}
QTabBar::tab:selected {
    background: #0B162C;
    color: #FFFFFF;
    border-bottom: 2px solid #1565C0;
}
QTabBar::tab:hover:!selected {
    color: #E8ECF1;
}

QStatusBar {
    background: #060E1A;
    color: #8FA4B8;
    border-top: 1px solid #1A3050;
}

/* NewConnectionDialog test-result frame */
QFrame#testResultFrame {
    border: 1px solid #2A4060;
    border-left-width: 4px;
    border-radius: 2px;
    background: #0F1E3D;
}
QFrame#testResultFrame[dataState="pending"] { border-left-color: #1565C0; }
QFrame#testResultFrame[dataState="success"] { border-left-color: #43A047; }
QFrame#testResultFrame[dataState="error"]   { border-left-color: #E53935; }
QLabel#testResultTitle {
    font-weight: 700;
    color: #FFFFFF;
}

/* Inspector */
QFrame#inspectorPanel {
    background: #0F1E3D;
    border: 1px solid #2A4060;
    border-radius: 3px;
}
QLabel#inspectorTitle {
    font-family: "Consolas", "Menlo", monospace;
    font-size: 14px;
    font-weight: 700;
    color: #FFFFFF;
}
QLabel#inspectorMeta {
    color: #8FA4B8;
    font-size: 11px;
}
QLabel#inspectorValue {
    font-family: "Consolas", "Menlo", monospace;
    font-size: 28px;
    font-weight: 700;
    color: #43A047;
}

/* Dialogs */
QMessageBox, QDialog {
    background: #0F1E3D;
    color: #E8ECF1;
}
QMessageBox QLabel, QDialog QLabel {
    color: #E8ECF1;
}
QMessageBox QPushButton, QDialog QPushButton {
    min-width: 80px;
    min-height: 24px;
}

/* Subnet scan dialog */
QProgressBar {
    background: #0F1E3D;
    border: 1px solid #2A4060;
    border-radius: 2px;
    text-align: center;
    color: #E8ECF1;
}
QProgressBar::chunk {
    background: #1565C0;
    border-radius: 1px;
}
"""
