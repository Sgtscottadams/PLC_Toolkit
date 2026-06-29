"""Domain models for plck.

These are pure dataclasses with no external dependencies so the rest of
the library and the GUI can use them without dragging in pylogix or
PySide6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TagDataType(str, Enum):
    """PLC data types we care about. Other types are surfaced as OTHER."""

    BOOL = "BOOL"
    SINT = "SINT"
    INT = "INT"
    DINT = "DINT"
    LINT = "LINT"
    USINT = "USINT"
    UINT = "UINT"
    UDINT = "UDINT"
    ULINT = "ULINT"
    REAL = "REAL"
    LREAL = "LREAL"
    STRING = "STRING"
    BYTE = "BYTE"
    WORD = "WORD"
    DWORD = "DWORD"
    LWORD = "LWORD"
    TIME = "TIME"
    LTIME = "LTIME"
    DATE = "DATE"
    TIME_OF_DAY = "TIME_OF_DAY"
    DATE_AND_TIME = "DATE_AND_TIME"
    UDT = "UDT"  # User-Defined Type - has members
    ARRAY = "ARRAY"  # 1-D or N-D array of another type
    OTHER = "OTHER"  # Anything we don't explicitly model


class ReadQuality(str, Enum):
    """Quality of a single read result. Maps to the OPC UA quality codes
    operators are familiar with."""

    GOOD = "Good"
    BAD = "Bad"  # PLC returned a CIP error or no response
    STALE = "Stale"  # Last successful read is older than the freshness window
    UNCERTAIN = "Uncertain"  # Got a response but it was partial or unexpected


@dataclass
class PlcConnection:
    """A connection to a specific PLC.

    `nickname` is a human label the operator picks (e.g. "Compressor Skid A").
    `ip`, `slot`, `port` are the wire parameters.
    `cip_path` is the advanced override — if set, it replaces `slot` in the
    CIP route. Most installations only need `slot`.
    """

    nickname: str = ""
    ip: str = ""
    slot: int = 0
    port: int = 44818
    cip_path: Optional[str] = None
    # Auto label from discovery (product name / IP). Shown as Device ID in
    # Connection Manager; distinct from the operator's friendly nickname.
    device_id: Optional[str] = None
    # Discovered-once facts, populated after a successful connection.
    vendor: Optional[str] = None
    product_name: Optional[str] = None
    revision: Optional[str] = None
    serial_number: Optional[str] = None
    last_scan: Optional[str] = None  # ISO 8601 UTC from plcs.last_scan

    def device_label(self) -> str:
        """Read-only device identifier for tables and fallbacks."""
        ip = (self.ip or "").strip()
        for val in (self.product_name, self.device_id):
            if not val:
                continue
            text = str(val).strip()
            if text and text != ip:
                return text
        return ip

    def device_display(self) -> str:
        """Plain-English family plus catalog, e.g. CompactLogix · 1769-L33ER."""
        from plck.device_filter import format_device_display

        source = self.product_name or self.device_id
        return format_device_display(source, ip=self.ip)

    def display_label(self) -> str:
        """Friendly workspace title: nickname when set, else device display."""
        nick = (self.nickname or "").strip()
        if nick:
            return nick
        return self.device_display() or self.ip

    def is_valid(self) -> bool:
        """Lightweight check before we try to connect. Returns True iff the
        IP looks reasonable. Nickname is optional. Doesn't attempt to resolve
        DNS or open a socket — that happens at connect-time.
        """
        if not self.ip or not str(self.ip).strip():
            return False
        # Allow IPv4 dotted quad or a hostname. Don't try to parse — pylogix
        # does its own validation at connect time.
        return True


@dataclass
class TagNode:
    """A single node in the tag tree.

    For UDT parent nodes: `data_type` is UDT, `udt_name` is the UDT type,
    `members` is a list of child TagNodes (recursive). For atomic types:
    `data_type` is BOOL/SINT/... and `members` is empty.

    `is_array` and `array_dim` describe array tags. pylogix's Tag has an
    `Array` field; we copy that into a flat dimension list (e.g. [4] for
    `array[4]`, [3, 4] for `array[3,4]`).
    """

    name: str  # Full tag path, e.g. "Pump_01.Speed" or "Program:MainProgram.Tag"
    data_type: TagDataType = TagDataType.OTHER
    udt_name: Optional[str] = None  # Set when data_type is UDT
    is_array: bool = False
    array_dim: list[int] = field(default_factory=list)
    members: list["TagNode"] = field(default_factory=list)

    # plc-side metadata:
    #   write_tag=True means the tag is a command/output. v2.0 is read-only
    #   so the GUI should not expose [+ Add to Monitor] for these. pylogix
    #   does NOT expose External Access flags; we infer write tags from the
    #   convention that the .C (configuration) and Cmd/Set suffixes are
    #   outputs. The compiler also has External Access = Read/Write but
    #   pylogix doesn't read that, so we mark conservatively: all non-I/O
    #   module tags are treated as read/write = read-only-in-v2.0 = False.
    is_write_tag: bool = False

    def walk(self):
        """Yield this node, then all members recursively (preorder)."""
        yield self
        for m in self.members:
            yield from m.walk()

    def count(self) -> int:
        """Total descendant count including self."""
        return 1 + sum(m.count() for m in self.members)

    def leaf_count(self) -> int:
        """Count of atomic leaves (no members)."""
        if not self.members:
            return 1
        return sum(m.leaf_count() for m in self.members)

    def find(self, full_name: str) -> Optional["TagNode"]:
        """Find a child node by full path. Returns None if not found."""
        if self.name == full_name:
            return self
        for m in self.members:
            r = m.find(full_name)
            if r is not None:
                return r
        return None


@dataclass
class TagTree:
    """A complete tag tree for one PLC, with provenance."""

    plc: PlcConnection
    root: list[TagNode]  # Top-level tags (e.g. "Pump_01", "Tank", "Program:MainProgram")
    discovered_at: str  # ISO 8601 UTC timestamp
    discovery_duration_s: float = 0.0

    def count(self) -> int:
        return sum(n.count() for n in self.root)

    def leaf_count(self) -> int:
        return sum(n.leaf_count() for n in self.root)

    def find(self, full_name: str) -> Optional[TagNode]:
        for n in self.root:
            r = n.find(full_name)
            if r is not None:
                return r
        return None

    def leaf_names(self) -> list[str]:
        """All atomic leaf tag names (for export, for the monitor list)."""
        out = []
        for n in self.root:
            for ln in n.walk():
                if not ln.members:  # atomic leaf
                    out.append(ln.name)
        return out


@dataclass
class ReadResult:
    """Result of a single Read() against a connected PLC."""

    tag_name: str
    value: object  # Python type — int, float, str, bool, bytes, list, or None
    data_type: TagDataType = TagDataType.OTHER
    quality: ReadQuality = ReadQuality.GOOD
    error: Optional[str] = None  # CIP error string when quality is BAD
    elapsed_ms: float = 0.0
