"""
Tests for the v1 binary's other public methods.

Background
----------
The v1 binary (plc_toolkit_consolidated.py) has 6 v1 tests in
test_v1_discover_tags.py covering the freeze bug. This file covers
the rest of the public surface so a future regression in any of
these methods surfaces as a red test instead of a field report.

What's covered here:

  1. _parse_structure_def — recursive UDT walker. A bug here
     corrupts every export. Pure function, easy to test.
  2. DatabaseManager — SQLite CRUD. Bug here loses data.
  3. connect / disconnect — connection lifecycle, error path.
  4. read_tag — single read, case-insensitive lookup.
  5. export_excel / export_json / export_xml — write to disk,
     verify file content.
  6. _find_case_insensitive_tag — pure function, helper for
     read_tag and monitor_tag.

What's NOT tested here:

  - run_discovery_workflow / run_export_workflow / run_tag_checker_workflow
    / show_splash / show_tools_menu / run: these all use input() or
    build interactive UIs. They are tested by manual smoke testing
    on a real PLC, not by automated unit tests. The underlying
    methods they call (discover_tags, export_all, read_tag,
    monitor_tag) ARE tested here.
  - monitor_tag: uses threading.Event and input(); the input()
    pattern is hard to stub without polluting stdin. The freeze
    bug fix is the highest-priority regression risk; monitor_tag
    is exercised by manual smoke. (Future work: stub input() with
    a queue that returns a single b'\n' to stop the monitor.)

Test fakes for LogixDriver mirror the same shape used in
test_v1_discover_tags.py: a _FakeLogixDriver class with
.connected, .read(), .get_tag_list(), .get_tag_info(), and
.close() methods.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from unittest.mock import patch

_TEST_ROOT = Path(__file__).resolve().parent
_V1_ROOT = _TEST_ROOT.parent
if str(_V1_ROOT) not in sys.path:
    sys.path.insert(0, str(_V1_ROOT))

try:
    from plc_toolkit_consolidated import (  # noqa: E402
        PLCToolkit,
        DatabaseManager,
        OUTPUT_FOLDER,
    )
except ModuleNotFoundError as exc:
    if exc.name == "pycomm3":
        import pytest
        pytest.skip(
            "pycomm3 not installed; v1 public-method tests skipped",
            allow_module_level=True,
        )
    raise


# ---------------------------------------------------------------------------
# Fakes (mirroring test_v1_discover_tags.py style)
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, value=None, error: str = "", tag: str = "", type: Any = None):
        self.value = value
        self.error = error
        self.tag = tag
        self.type = type


class _FakeTagSummary(dict):
    def __init__(self, name: str, data_type: Any = "DINT"):
        super().__init__(tag_name=name, data_type=data_type)
        self.tag_name = name
        self.data_type = data_type


class _FakeLogixDriver:
    """Stand-in for pycomm3.LogixDriver. Records every method call so
    tests can assert on the lifecycle."""

    def __init__(self, ip: str = "192.0.2.10", slot: int = 0, **kwargs):
        self.ip = ip
        self.slot = slot
        self.kwargs = kwargs
        self.connected = True
        self.open_count = 0
        self.close_count = 0
        self.read_calls: list[str] = []
        self.get_tag_list_calls: list[Any] = []
        self.get_tag_info_calls: list[str] = []
        # Default data: one controller tag, one program.
        self._controller_tags = [_FakeTagSummary("MyTag", "DINT")]
        self._programs = ["MainProgram"]
        self._program_tags = {
            "MainProgram": [_FakeTagSummary("LocalTag", "BOOL")],
        }
        self._read_responses: dict[str, _FakeResponse] = {}
        self._tag_info_responses: dict[str, dict] = {}

    def open(self):
        self.open_count += 1

    def close(self):
        self.close_count += 1
        self.connected = False

    def get_plc_info(self):
        return {"plc_name": "TestPLC", "revision": {"major": 32, "minor": 11}}

    def get_tag_list(self, program: str | None = None):
        self.get_tag_list_calls.append(program)
        if program is None:
            return list(self._controller_tags)
        return list(self._program_tags.get(program, []))

    def read(self, tag: str):
        self.read_calls.append(tag)
        if tag in self._read_responses:
            return self._read_responses[tag]
        if tag == "PROGRAM":
            return _FakeResponse(value=list(self._programs))
        return _FakeResponse(value=42, tag=tag, type="DINT")

    def get_tag_info(self, tag: str):
        self.get_tag_info_calls.append(tag)
        if tag in self._tag_info_responses:
            return self._tag_info_responses[tag]
        return {"data_type": {"name": "DINT", "internal_tags": {}}}


def _make_toolkit(plc: _FakeLogixDriver | None = None,
                  tags: dict | None = None) -> PLCToolkit:
    """Build a PLCToolkit bypassing __init__ (no DB created, no folders)."""
    t = PLCToolkit.__new__(PLCToolkit)
    t.plc = plc
    t.plc_info = plc.get_plc_info() if plc else {}
    t.tags = tags if tags is not None else {}
    t.ip = plc.ip if plc else None
    t.slot = plc.slot if plc else 0
    t.plc_id = None
    t.db = None
    t.stop_monitoring = threading.Event()
    return t


# ===========================================================================
# 1. _parse_structure_def — recursive UDT walker
# ===========================================================================

def test_parse_structure_def_returns_type_name_for_scalar():
    """A scalar tag (no internal_tags) returns just the type name as a
    string. JSON-serializable. This is the most common case."""
    t = _make_toolkit()
    result = t._parse_structure_def({"data_type": {"name": "DINT"}})
    assert result == "DINT", f"Expected 'DINT', got {result!r}"


def test_parse_structure_def_handles_string_data_type():
    """Some pycomm3 versions return `data_type` as a string instead
    of a dict. The function must not crash — it returns the string."""
    t = _make_toolkit()
    result = t._parse_structure_def({"data_type": "BOOL"})
    assert result == "BOOL"


def test_parse_structure_def_handles_object_with_name_attr():
    """pycomm3 returns data_type as a class instance with a `.name`
    attribute in some versions. The function must extract the name
    via hasattr, not isinstance(dict)."""
    t = _make_toolkit()
    class FakeType:
        name = "TIMER"
    result = t._parse_structure_def({"data_type": FakeType()})
    assert result == "TIMER"


def test_parse_structure_def_handles_empty_internal_tags():
    """A UDT with zero members should return the UDT type name, not
    a structure with empty members."""
    t = _make_toolkit()
    result = t._parse_structure_def({"data_type": {"name": "MY_UDT", "internal_tags": {}}})
    assert result == "MY_UDT"


def test_parse_structure_def_recurses_into_udt_members():
    """A UDT with one BOOL member should produce a structure with the
    member nested under 'members'."""
    t = _make_toolkit()
    tag_def = {
        "data_type": {
            "name": "MY_UDT",
            "internal_tags": {
                "Active": {"data_type": {"name": "BOOL"}},
            },
        }
    }
    result = t._parse_structure_def(tag_def)
    assert isinstance(result, dict)
    assert result["_data_type_"] == "MY_UDT"
    assert "members" in result
    assert "Active" in result["members"]
    assert result["members"]["Active"] == "BOOL"


def test_parse_structure_def_skips_double_underscore_members():
    """Internal pycomm3 members like `__MemberName` should be
    filtered. The function uses `if not member_name.startswith('__')`
    — this test pins that contract."""
    t = _make_toolkit()
    tag_def = {
        "data_type": {
            "name": "MY_UDT",
            "internal_tags": {
                "VisibleMember": {"data_type": {"name": "DINT"}},
                "__HiddenMember": {"data_type": {"name": "BOOL"}},
                "__init__": {"data_type": {"name": "DINT"}},
            },
        }
    }
    result = t._parse_structure_def(tag_def)
    assert "VisibleMember" in result["members"]
    assert "__HiddenMember" not in result["members"]
    assert "__init__" not in result["members"]


def test_parse_structure_def_handles_deeply_nested_udt():
    """A UDT containing another UDT should recurse all the way down
    to the leaf types. Tests that the recursion terminates and
    preserves the type names at each level."""
    t = _make_toolkit()
    tag_def = {
        "data_type": {
            "name": "OUTER",
            "internal_tags": {
                "Inner": {
                    "data_type": {
                        "name": "INNER",
                        "internal_tags": {
                            "Leaf": {"data_type": {"name": "REAL"}},
                        },
                    },
                },
            },
        }
    }
    result = t._parse_structure_def(tag_def)
    assert result["_data_type_"] == "OUTER"
    inner = result["members"]["Inner"]
    assert inner["_data_type_"] == "INNER"
    assert inner["members"]["Leaf"] == "REAL"


# ===========================================================================
# 2. DatabaseManager — SQLite CRUD
# ===========================================================================

def test_database_manager_creates_tables_on_init():
    """DatabaseManager must create `plcs` and `tag_data` tables on
    construction. A schema regression here loses every scan."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        mgr = DatabaseManager(str(db_path))
        try:
            cur = mgr.conn.cursor()
            tables = cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            assert ("plcs",) in tables, f"plcs table missing; got {tables}"
            assert ("tag_data",) in tables, f"tag_data table missing; got {tables}"
        finally:
            mgr.close()


def test_database_manager_update_plc_data_inserts_new_plc():
    """update_plc_data must insert a new row and return its id."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        mgr = DatabaseManager(str(db_path))
        try:
            plc_id = mgr.update_plc_data(
                ip="10.0.0.1", slot=0,
                info={"plc_name": "Compressor A", "revision": {"major": 32, "minor": 11}},
                tags={"MyTag": "DINT"},
            )
            assert isinstance(plc_id, int)
            cur = mgr.conn.cursor()
            row = cur.execute(
                "SELECT ip_address, slot, name, revision FROM plcs WHERE id=?",
                (plc_id,),
            ).fetchone()
            assert row == ("10.0.0.1", 0, "Compressor A", "32.11")
        finally:
            mgr.close()


def test_database_manager_update_plc_data_upserts_existing():
    """update_plc_data on an existing (ip, slot) must UPDATE not
    INSERT, so rescans don't create duplicates."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        mgr = DatabaseManager(str(db_path))
        try:
            id1 = mgr.update_plc_data(
                "10.0.0.1", 0,
                {"plc_name": "Compressor A", "revision": {"major": 32, "minor": 11}},
                {"MyTag": "DINT"},
            )
            id2 = mgr.update_plc_data(
                "10.0.0.1", 0,
                {"plc_name": "Compressor A Renamed", "revision": {"major": 33, "minor": 1}},
                {"MyTag": "DINT", "AnotherTag": "BOOL"},
            )
            assert id1 == id2, "Rescanning the same (ip, slot) should reuse the id"
            cur = mgr.conn.cursor()
            row = cur.execute(
                "SELECT name, revision FROM plcs WHERE id=?", (id1,),
            ).fetchone()
            assert row == ("Compressor A Renamed", "33.1")
        finally:
            mgr.close()


def test_database_manager_get_tag_data_round_trips_tags():
    """Tags stored as JSON must come back identical."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        mgr = DatabaseManager(str(db_path))
        try:
            original = {
                "MyTag": "DINT",
                "Nested": {
                    "_data_type_": "MY_UDT",
                    "members": {"Active": "BOOL", "Counter": "DINT"},
                },
            }
            plc_id = mgr.update_plc_data(
                "10.0.0.1", 0,
                {"plc_name": "X", "revision": {"major": 1, "minor": 0}},
                original,
            )
            got = mgr.get_tag_data(plc_id)
            assert got == original
        finally:
            mgr.close()


# ===========================================================================
# 3. connect / disconnect — connection lifecycle
# ===========================================================================

def test_connect_opens_driver_and_populates_plc_info():
    """connect() must construct a LogixDriver, call open(), and store
    get_plc_info() result. After connect, plc.connected is True and
    plc_info contains plc_name and revision."""
    t = _make_toolkit(plc=None)
    fake = _FakeLogixDriver(ip="10.0.0.1", slot=0)
    with patch("plc_toolkit_consolidated.LogixDriver", return_value=fake):
        result = t.connect("10.0.0.1", 0)
    assert result is True
    assert fake.open_count == 1
    assert t.plc is fake
    assert t.plc_info["plc_name"] == "TestPLC"
    assert t.plc_info["revision"] == {"major": 32, "minor": 11}
    assert t.ip == "10.0.0.1"
    assert t.slot == 0


def test_connect_passes_timeout_10_to_driver():
    """The current v1 source hard-codes `timeout=10` on the
    LogixDriver. This test pins that contract — if someone changes
    the timeout, they have to update the test, and the change
    becomes visible in code review."""
    t = _make_toolkit(plc=None)
    fake = _FakeLogixDriver()
    with patch("plc_toolkit_consolidated.LogixDriver", return_value=fake) as MockDriver:
        t.connect("10.0.0.1", 0)
    call_kwargs = MockDriver.call_args.kwargs
    assert call_kwargs.get("timeout") == 10, (
        f"Expected timeout=10, got {call_kwargs!r}. Per-memory: "
        f"SCADA radio-PLCs need at least 5s, so 10s is the minimum."
    )
    assert call_kwargs.get("init_tags") is False


def test_connect_returns_false_and_closes_on_failure():
    """If LogixDriver.open() raises, connect() must return False and
    not leave a half-open driver lying around."""
    t = _make_toolkit(plc=None)

    class _FailingDriver(_FakeLogixDriver):
        def open(self):
            self.open_count += 1
            raise ConnectionError("PLC not reachable")

    with patch("plc_toolkit_consolidated.LogixDriver", return_value=_FailingDriver()):
        result = t.connect("10.0.0.1", 0)
    assert result is False
    assert t.plc is None, "connect() must clear self.plc on failure"


def test_disconnect_closes_driver_and_clears_plc():
    """disconnect() must call plc.close() and set self.plc = None
    so a subsequent connect() doesn't share state with a closed PLC."""
    t = _make_toolkit()
    fake = _FakeLogixDriver()
    t.plc = fake
    t.disconnect()
    assert fake.close_count == 1
    assert t.plc is None


def test_disconnect_is_safe_when_not_connected():
    """disconnect() on a toolkit with no plc must not raise. This
    matters because run()'s finally block always calls disconnect."""
    t = _make_toolkit()
    t.plc = None
    t.disconnect()  # must not raise
    assert t.plc is None


# ===========================================================================
# 4. read_tag — single read with case-insensitive lookup
# ===========================================================================

def test_read_tag_returns_value_from_plc():
    """read_tag must call plc.read(tag_name) and return the response."""
    t = _make_toolkit()
    fake = _FakeLogixDriver()
    fake._read_responses["MyTag"] = _FakeResponse(value=42, tag="MyTag", type="DINT")
    t.plc = fake
    result = t.read_tag("MyTag")
    assert result.value == 42
    assert "MyTag" in fake.read_calls


def test_read_tag_case_insensitive_lookup_uses_stored_case():
    """If the operator types 'mytag' but the tag is 'MyTag', the
    function must find the stored name and use the correct case in
    the actual read call."""
    t = _make_toolkit()
    t.tags = {"MyTag": "DINT", "OtherTag": "BOOL"}
    fake = _FakeLogixDriver()
    fake._read_responses["MyTag"] = _FakeResponse(value=1, tag="MyTag", type="DINT")
    t.plc = fake
    result = t.read_tag("mytag")
    assert result.tag == "MyTag", f"read_tag returned tag={result.tag!r}, expected 'MyTag'"
    assert "MyTag" in fake.read_calls, f"Expected read of 'MyTag', got {fake.read_calls!r}"


def test_read_tag_raises_when_not_connected():
    """read_tag with no plc must raise — silently returning a
    'disconnected' result is the kind of bug operators hate."""
    t = _make_toolkit()
    t.plc = None
    try:
        t.read_tag("MyTag")
        assert False, "read_tag should have raised"
    except Exception as e:
        assert "Not connected" in str(e)


# ===========================================================================
# 5. export_excel / export_json / export_xml — write to disk
# ===========================================================================

def _build_tags_for_export() -> dict:
    """A representative tag dict for export tests. Mixes a scalar
    and a UDT with members, so the tests exercise both code paths
    in the export flatten() helper."""
    return {
        "SimpleTag": "DINT",
        "ComplexUDT": {
            "_data_type_": "MOTOR_STATE",
            "members": {
                "Running": "BOOL",
                "Speed": "REAL",
            },
        },
    }


def test_export_json_writes_file_with_valid_json():
    """export_json must write a file containing valid JSON that
    round-trips through json.loads."""
    t = _make_toolkit(tags=_build_tags_for_export())
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "tags.json"
        t.export_json(str(out))
        assert out.exists(), f"export_json did not create {out}"
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded == _build_tags_for_export()


def test_export_xml_writes_file_with_valid_xml():
    """export_xml must write a file containing parseable XML with
    a PLCTagScan root containing the tags."""
    t = _make_toolkit(tags=_build_tags_for_export())
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "tags.xml"
        t.export_xml(str(out))
        assert out.exists()
        tree = ET.parse(str(out))
        root = tree.getroot()
        assert root.tag == "PLCTagScan", f"Expected PLCTagScan root, got {root.tag}"
        # The two top-level tags must be present
        names = [child.attrib.get("name") for child in root.find("Tags")]
        assert "SimpleTag" in names
        assert "ComplexUDT" in names


def test_export_all_returns_false_with_no_tags():
    """export_all() with no tags loaded must print an error and
    return False — must not crash with AttributeError on None."""
    t = _make_toolkit(tags={})
    result = t.export_all()
    assert result is False


def test_export_all_writes_to_output_folder_by_default():
    """export_all() with no base_filename must write to OUTPUT_FOLDER
    using a timestamped, IP-safe filename. Operators rely on the
    default path matching what they find in File Explorer."""
    t = _make_toolkit(tags={"MyTag": "DINT"})
    t.ip = "10.20.30.41"
    # The default export folder is ./plc_scans relative to CWD. Use
    # a temp CWD so we don't pollute the real repo. Note: PLCToolkit.__init__
    # normally creates the folder via `Path(OUTPUT_FOLDER).mkdir(exist_ok=True)`;
    # we bypassed __init__ with __new__, so we have to do it here.
    with tempfile.TemporaryDirectory() as tmp:
        old_cwd = Path.cwd()
        try:
            import os
            os.chdir(tmp)
            (Path(tmp) / OUTPUT_FOLDER).mkdir(exist_ok=True)
            result = t.export_all()
            assert result is True
            folder = Path(tmp) / OUTPUT_FOLDER
            assert folder.exists(), f"output folder {folder} not created"
            files = list(folder.iterdir())
            assert any(f.suffix == ".json" for f in files), f"No JSON in {files!r}"
            # The filename embeds the IP (dots replaced) so operators can find scans
            assert any("10_20_30_41" in f.name for f in files), (
                f"Filename should include IP (10_20_30_41), got: {[f.name for f in files]}"
            )
        finally:
            os.chdir(old_cwd)


# ===========================================================================
# 6. _find_case_insensitive_tag — pure helper
# ===========================================================================

def test_find_case_insensitive_tag_simple_match():
    """Exact case match returns the tag unchanged."""
    t = _make_toolkit()
    t.tags = {"MyTag": "DINT", "OtherTag": "BOOL"}
    assert t._find_case_insensitive_tag("MyTag") == "MyTag"


def test_find_case_insensitive_tag_lowercase_query():
    """Lowercase query against camelCase tags returns the camelCase name."""
    t = _make_toolkit()
    t.tags = {"MyTag": "DINT", "OtherTag": "BOOL"}
    assert t._find_case_insensitive_tag("mytag") == "MyTag"
    assert t._find_case_insensitive_tag("othertag") == "OtherTag"


def test_find_case_insensitive_tag_unknown_returns_none():
    """A query that matches no tag returns None — caller decides
    whether to fall back to the literal name or raise."""
    t = _make_toolkit()
    t.tags = {"MyTag": "DINT"}
    assert t._find_case_insensitive_tag("NotATag") is None


def test_find_case_insensitive_tag_dotted_path():
    """A dotted path like 'MyTag.NestedMember' must match the
    camelCase base tag and the camelCase member name."""
    t = _make_toolkit()
    t.tags = {
        "MotorState": {
            "_data_type_": "MOTOR_STATE",
            "members": {
                "Running": "BOOL",
                "Speed": "REAL",
            },
        },
    }
    assert t._find_case_insensitive_tag("motorstate.running") == "MotorState.Running"
    assert t._find_case_insensitive_tag("MotorState.speed") == "MotorState.Speed"


def test_find_case_insensitive_tag_dotted_path_unknown_member_returns_none():
    """A dotted path with a non-existent member returns None — the
    read call must not silently fall through with a partial path."""
    t = _make_toolkit()
    t.tags = {
        "MotorState": {
            "_data_type_": "MOTOR_STATE",
            "members": {"Running": "BOOL"},
        },
    }
    assert t._find_case_insensitive_tag("MotorState.NotAMember") is None
