"""plc_toolkit.ui — Qt widgets for the v2.0 GUI.

Each view is a QWidget subclass. They emit Qt signals to coordinate
with the MainWindow and with each other. The workers live in
plc_toolkit.workers (separate package) so the UI code stays free of
plck imports where possible — though views that need to format
plck.model values (like TagNode, ReadResult) import them.
"""

from plc_toolkit.ui.connection_view import ConnectionView
from plc_toolkit.ui.workspace_view import WorkspaceView
from plc_toolkit.ui.new_connection_dialog import NewConnectionDialog

__all__ = ["ConnectionView", "WorkspaceView", "NewConnectionDialog"]
