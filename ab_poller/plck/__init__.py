"""plck — PLC Toolkit Core Library.

A clean, testable Python library for Allen-Bradley PLC tag discovery,
export, and live monitoring over EtherNet/IP. v2.0 uses pylogix
(replacing the v1 pycomm3-based implementation).

Public API:
    plck.comms.PLCClient        -- thread-safe pylogix wrapper
    plck.discovery.discover_tags -- build a tag tree for a connected PLC
    plck.export.export_tags     -- write a tag tree to Excel/JSON/XML
    plck.db.DatabaseManager     -- SQLite persistence (v1 schema compatible)

Threading rule (from pylogix docs):
    pylogix is NOT thread-safe across shared instances. Each worker
    thread or QThread must own its own PLCClient. Do not pass a single
    client across threads.
"""

__version__ = "2.0.0"

from plck.models import PlcConnection, TagNode, TagTree, TagDataType, ReadQuality
from plck.errors import PlcError, PlcTimeout, PlcAuthError, PlcUnsupported

# Import submodules so the advertised public API (e.g.
# `plck.discovery.discover_tags`, `plck.comms.PLCClient`) resolves without the
# caller having to `import plck.discovery` explicitly. Worker code references
# `plck.discovery.discover_tags(...)`; without these imports that attribute
# access raises AttributeError("module 'plck' has no attribute 'discovery'").
from plck import comms, discovery, export, db  # noqa: E402,F401

__all__ = [
    "PlcConnection",
    "TagNode",
    "TagTree",
    "TagDataType",
    "ReadQuality",
    "PlcError",
    "PlcTimeout",
    "PlcAuthError",
    "PlcUnsupported",
    "comms",
    "discovery",
    "export",
    "db",
]
