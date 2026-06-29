"""plck.db — SQLite persistence for connections and tag snapshots.

Schema is INTENTIONALLY compatible with the v1 TUI
(`plc_toolkit_consolidated.py`) so an operator who has been using v1
can drop their existing `plc_data.db` into a v2 install and not lose
anything.

Tables:
    plcs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip TEXT NOT NULL,
        slot INTEGER NOT NULL DEFAULT 0,
        name TEXT NOT NULL,                -- v1 "name" = v2 "nickname"
        revision TEXT,
        last_scan TEXT,                    -- ISO 8601 UTC; nullable if never scanned
        product_name TEXT,                 -- v2.0 additions
        serial_number TEXT,                -- v2.0 additions
        port INTEGER NOT NULL DEFAULT 44818,  -- v2.0 additions
        cip_path TEXT,                     -- v2.0 additions
        UNIQUE(ip, slot)
    )

    tag_data(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plc_id INTEGER NOT NULL,
        scan_timestamp TEXT NOT NULL,      -- ISO 8601 UTC
        tags_json TEXT NOT NULL,           -- JSON: array of {path, type, members, ...}
        FOREIGN KEY(plc_id) REFERENCES plcs(id) ON DELETE CASCADE
    )

    scan_history(                       -- v2.0: track every scan, not just the latest
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plc_id INTEGER NOT NULL,
        scan_timestamp TEXT NOT NULL,
        tag_count INTEGER NOT NULL,
        duration_s REAL,
        source TEXT NOT NULL DEFAULT 'manual',  -- 'manual' | 're-discover' | 'scheduled'
        notes TEXT,
        FOREIGN KEY(plc_id) REFERENCES plcs(id) ON DELETE CASCADE
    )

The `tags_json` column carries a JSON-serialized tag tree in the same
shape as the v1 TUI used. The TUI's `export_to_*` writers consumed that
exact JSON, so the v2 export pipeline is the same.

Usage:
    db = DatabaseManager()                       # uses default path
    db = DatabaseManager(path="/tmp/foo.db")     # explicit path
    db.upsert_plc(plc)
    db.save_tag_snapshot(plc_id, tree, source="re-discover")
    history = db.list_scans(plc_id)
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from plck.models import PlcConnection, TagTree


def _utcnow_iso() -> str:
    """Return current UTC time as an ISO 8601 string with 'Z' suffix.

    Matches the v1 TUI's `datetime.utcnow().isoformat() + 'Z'` format so
    saved scans from v1 still display correctly in v2.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _default_db_path() -> str:
    """Default location: %APPDATA%/PLCToolkit/plc_data.db on Windows,
    ~/.local/share/PLCToolkit/plc_data.db on Linux. Matches the v1 TUI's
    path logic.
    """
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "PLCToolkit", "plc_data.db")
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "PLCToolkit", "plc_data.db")


class DatabaseManager:
    """SQLite-backed store for PLC connections and tag snapshots.

    Threading: SQLite connections are not safe to share across threads.
    Each thread should construct its own DatabaseManager (cheap — it's
    just a connection). The TUI did the same thing; the GUI follows.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS plcs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip TEXT NOT NULL,
        slot INTEGER NOT NULL DEFAULT 0,
        name TEXT NOT NULL,
        revision TEXT,
        last_scan TEXT,
        product_name TEXT,
        serial_number TEXT,
        port INTEGER NOT NULL DEFAULT 44818,
        cip_path TEXT,
        device_id TEXT,
        UNIQUE(ip, slot)
    );

    CREATE TABLE IF NOT EXISTS tag_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plc_id INTEGER NOT NULL,
        scan_timestamp TEXT NOT NULL,
        tags_json TEXT NOT NULL,
        FOREIGN KEY(plc_id) REFERENCES plcs(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS scan_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plc_id INTEGER NOT NULL,
        scan_timestamp TEXT NOT NULL,
        tag_count INTEGER NOT NULL,
        duration_s REAL,
        source TEXT NOT NULL DEFAULT 'manual',
        notes TEXT,
        FOREIGN KEY(plc_id) REFERENCES plcs(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_tag_data_plc
        ON tag_data(plc_id, scan_timestamp DESC);
    CREATE INDEX IF NOT EXISTS idx_scan_history_plc
        ON scan_history(plc_id, scan_timestamp DESC);
    """

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or _default_db_path()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.executescript(self.SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Apply additive schema changes for existing databases."""
        try:
            self.conn.execute(
                "ALTER TABLE tag_data ADD COLUMN values_json TEXT"
            )
        except sqlite3.OperationalError:
            pass  # column already present
        try:
            self.conn.execute(
                "ALTER TABLE plcs ADD COLUMN device_id TEXT"
            )
        except sqlite3.OperationalError:
            pass  # column already present
        self.conn.execute(
            """UPDATE plcs SET device_id = COALESCE(NULLIF(device_id, ''), product_name, name)
               WHERE device_id IS NULL OR device_id = ''"""
        )
        # Repair rows where device_id was stored as the IP despite a catalog name.
        self.conn.execute(
            """UPDATE plcs SET device_id = product_name
               WHERE product_name IS NOT NULL AND TRIM(product_name) != ''
                 AND (device_id IS NULL OR TRIM(device_id) = '' OR device_id = ip)"""
        )

    @staticmethod
    def _row_to_plc(row: sqlite3.Row) -> PlcConnection:
        keys = row.keys()
        device_id = row["device_id"] if "device_id" in keys else None
        return PlcConnection(
            nickname=row["name"],
            ip=row["ip"],
            slot=row["slot"],
            port=row["port"],
            cip_path=row["cip_path"],
            device_id=device_id,
            product_name=row["product_name"],
            revision=row["revision"],
            serial_number=row["serial_number"],
            last_scan=row["last_scan"],
        )

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # -- PLC connections -------------------------------------------------

    def upsert_plc(self, plc: PlcConnection) -> int:
        """Insert a new PLC or update the existing one (matched on ip+slot).

        Returns the row id. Discovery-derived fields (revision,
        product_name, serial_number) are updated only if non-None, so a
        connect that hasn't been attempted yet doesn't clobber the
        previous values.
        """
        existing = self.conn.execute(
            "SELECT id, name FROM plcs WHERE ip = ? AND slot = ?",
            (plc.ip, plc.slot),
        ).fetchone()
        catalog = self._catalog_name(plc)
        device_id = catalog if catalog else (None if existing else plc.ip)
        if existing is None:
            cur = self.conn.execute(
                """INSERT INTO plcs
                    (ip, slot, name, port, cip_path, device_id,
                     product_name, revision, serial_number, last_scan)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    plc.ip, plc.slot, plc.nickname or "", plc.port, plc.cip_path,
                    device_id,
                    plc.product_name, plc.revision, plc.serial_number, None,
                ),
            )
            self.conn.commit()
            return int(cur.lastrowid)
        else:
            # Update discovery fields only — nickname is edited separately
            # via update_plc_nickname() so rescans don't clobber it.
            self.conn.execute(
                """UPDATE plcs SET
                    port = COALESCE(?, port),
                    cip_path = COALESCE(?, cip_path),
                    device_id = COALESCE(?, device_id),
                    product_name = COALESCE(?, product_name),
                    revision = COALESCE(?, revision),
                    serial_number = COALESCE(?, serial_number)
                  WHERE id = ?""",
                (
                    plc.port, plc.cip_path, device_id,
                    plc.product_name, plc.revision, plc.serial_number,
                    int(existing["id"]),
                ),
            )
            self.conn.commit()
            return int(existing["id"])

    @staticmethod
    def _catalog_name(plc: PlcConnection) -> Optional[str]:
        """Return the controller catalog (e.g. 1756-L83E), never the IP."""
        ip = (plc.ip or "").strip()
        for val in (plc.product_name, plc.device_id):
            if not val:
                continue
            text = str(val).strip()
            if text and text != ip:
                return text
        return None

    def update_plc_nickname(self, ip: str, slot: int, nickname: str) -> None:
        """Persist the operator's friendly name for a saved connection."""
        self.conn.execute(
            "UPDATE plcs SET name = ? WHERE ip = ? AND slot = ?",
            (nickname, ip, slot),
        )
        self.conn.commit()

    def list_plcs(self) -> list[PlcConnection]:
        rows = self.conn.execute(
            "SELECT * FROM plcs ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [self._row_to_plc(r) for r in rows]

    def get_plc(self, ip: str, slot: int) -> Optional[PlcConnection]:
        r = self.conn.execute(
            "SELECT * FROM plcs WHERE ip = ? AND slot = ?", (ip, slot)
        ).fetchone()
        if r is None:
            return None
        return self._row_to_plc(r)

    def remove_plc(self, ip: str, slot: int) -> int:
        """Delete a PLC and all its scans. Returns the number of PLC rows
        deleted (0 or 1)."""
        cur = self.conn.execute(
            "DELETE FROM plcs WHERE ip = ? AND slot = ?", (ip, slot)
        )
        self.conn.commit()
        return cur.rowcount

    # -- Tag snapshots ---------------------------------------------------

    def save_tag_snapshot(
        self,
        plc_id: int,
        tree: TagTree,
        source: str = "manual",
        notes: Optional[str] = None,
    ) -> int:
        """Persist the latest tag tree and a scan_history row.

        Returns the scan_history row id. The previous `tag_data` row for
        this PLC is left in place — history is preserved.
        """
        tags_json = json.dumps(_serialize_tree(tree), separators=(",", ":"))
        ts = tree.discovered_at
        self.conn.execute(
            "INSERT INTO tag_data (plc_id, scan_timestamp, tags_json) VALUES (?, ?, ?)",
            (plc_id, ts, tags_json),
        )
        cur = self.conn.execute(
            """INSERT INTO scan_history
                (plc_id, scan_timestamp, tag_count, duration_s, source, notes)
                VALUES (?, ?, ?, ?, ?, ?)""",
            (
                plc_id, ts, tree.count(), tree.discovery_duration_s,
                source, notes,
            ),
        )
        self.conn.execute(
            "UPDATE plcs SET last_scan = ? WHERE id = ?",
            (ts, plc_id),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def load_latest_tags(self, plc_id: int) -> Optional[TagTree]:
        """Load the most recent tag snapshot for a PLC.

        Returns None if no scan has been recorded.
        """
        r = self.conn.execute(
            """SELECT tags_json, scan_timestamp FROM tag_data
               WHERE plc_id = ?
               ORDER BY scan_timestamp DESC LIMIT 1""",
            (plc_id,),
        ).fetchone()
        if r is None:
            return None
        payload = json.loads(r["tags_json"])
        plc_row = self.conn.execute(
            "SELECT * FROM plcs WHERE id = ?", (plc_id,)
        ).fetchone()
        plc = self._row_to_plc(plc_row)
        return _deserialize_tree(plc, payload, r["scan_timestamp"])

    def list_scans(self, plc_id: int, limit: int = 100) -> list[dict]:
        """List scan history for a PLC, newest first.

        Each row: {id, scan_timestamp, tag_count, duration_s, source, notes}.
        """
        rows = self.conn.execute(
            """SELECT id, scan_timestamp, tag_count, duration_s, source, notes
               FROM scan_history WHERE plc_id = ?
               ORDER BY scan_timestamp DESC LIMIT ?""",
            (plc_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def load_scan(self, scan_id: int) -> Optional[TagTree]:
        """Load a specific historical scan by scan_history.id."""
        r = self.conn.execute(
            """SELECT t.tags_json, t.scan_timestamp, t.plc_id
               FROM scan_history s JOIN tag_data t ON t.plc_id = s.plc_id
                 AND t.scan_timestamp = s.scan_timestamp
               WHERE s.id = ?""",
            (scan_id,),
        ).fetchone()
        if r is None:
            return None
        payload = json.loads(r["tags_json"])
        plc_row = self.conn.execute(
            "SELECT * FROM plcs WHERE id = ?", (r["plc_id"],)
        ).fetchone()
        plc = self._row_to_plc(plc_row)
        return _deserialize_tree(plc, payload, r["scan_timestamp"])

    def save_scan_values(self, scan_id: int, values: dict) -> None:
        """Persist leaf tag values read during/after a discovery scan."""
        if not values:
            return
        row = self.conn.execute(
            "SELECT plc_id, scan_timestamp FROM scan_history WHERE id = ?",
            (scan_id,),
        ).fetchone()
        if row is None:
            return
        payload = json.dumps(_serialize_values(values), separators=(",", ":"))
        self.conn.execute(
            """UPDATE tag_data SET values_json = ?
               WHERE plc_id = ? AND scan_timestamp = ?""",
            (payload, row["plc_id"], row["scan_timestamp"]),
        )
        self.conn.commit()

    def load_scan_values(self, scan_id: int) -> dict[str, object]:
        """Return saved tag values for a scan, or {} if none were stored."""
        r = self.conn.execute(
            """SELECT t.values_json
               FROM scan_history s JOIN tag_data t ON t.plc_id = s.plc_id
                 AND t.scan_timestamp = s.scan_timestamp
               WHERE s.id = ?""",
            (scan_id,),
        ).fetchone()
        if r is None or not r["values_json"]:
            return {}
        try:
            raw = json.loads(r["values_json"])
            return raw if isinstance(raw, dict) else {}
        except json.JSONDecodeError:
            return {}

    def update_scan_notes(self, scan_id: int, notes: str) -> None:
        self.conn.execute(
            "UPDATE scan_history SET notes = ? WHERE id = ?",
            (notes.strip() or None, scan_id),
        )
        self.conn.commit()


def _serialize_values(values: dict) -> dict:
    out = {}
    for key, val in values.items():
        if isinstance(val, (int, float, bool, str)) or val is None:
            out[key] = val
        else:
            out[key] = repr(val)
    return out


def _serialize_node(node) -> dict:
    out = {
        "name": node.name,
        "data_type": node.data_type.value,
    }
    if node.udt_name:
        out["udt_name"] = node.udt_name
    if node.is_array:
        out["is_array"] = True
        out["array_dim"] = list(node.array_dim)
    if node.is_write_tag:
        out["is_write_tag"] = True
    if node.members:
        out["members"] = [_serialize_node(m) for m in node.members]
    return out


def _serialize_tree(tree: TagTree) -> list[dict]:
    return [_serialize_node(n) for n in tree.root]


def _deserialize_node(payload: dict) -> "TagNode":
    from plck.models import TagNode, TagDataType
    return TagNode(
        name=payload["name"],
        data_type=TagDataType(payload.get("data_type", "OTHER")),
        udt_name=payload.get("udt_name"),
        is_array=bool(payload.get("is_array", False)),
        array_dim=list(payload.get("array_dim", [])),
        is_write_tag=bool(payload.get("is_write_tag", False)),
        members=[_deserialize_node(m) for m in payload.get("members", [])],
    )


def _deserialize_tree(plc: PlcConnection, payload: list, ts: str) -> TagTree:
    from plck.models import TagTree
    return TagTree(
        plc=plc,
        root=[_deserialize_node(p) for p in payload],
        discovered_at=ts,
    )
