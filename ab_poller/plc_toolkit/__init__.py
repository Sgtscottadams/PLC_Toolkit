"""plc_toolkit — the v2.0 GUI application.

Run with:
    python -m plc_toolkit

Or:
    python plc_toolkit/app.py

The application is split into:
    app.py        -- QApplication entry point, MainWindow
    ui/           -- QWidget subclasses for each view
    workers/      -- QThread-based workers for PLC I/O
"""

__version__ = "2.0.0"
