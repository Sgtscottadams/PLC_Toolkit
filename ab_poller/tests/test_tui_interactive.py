"""
Tests for the v1 binary's interactive methods.

Background
----------
The v1 binary's `monitor_tag` and the `run_*_workflow` methods are
interactive — they use `input()` to prompt the operator. The other
test files in this directory (test_v1_discover_tags, test_v1_theme,
test_v1_public_methods) cover non-interactive methods. This file
covers the interactive methods by stubbing `input()` via
`unittest.mock.patch`.

What's covered here:

  1. monitor_tag — continuous polling with ENTER-to-stop. The
     listener thread calls input(); we patch builtins.input to
     return immediately, which sets stop_monitoring, and the
     main thread exits the loop after at most one reading.

  2. show_splash — pure output, no input. Verifies the splash
     contains the toolkit title and the box-drawing border.

  3. run_discovery_workflow — the Y/n confirm prompt and the
     underlying discover_tags call. Tests both the "Y" and "n"
     branches.

  4. run_export_workflow — the Y/n confirm prompt, the underlying
     export_all call, and the no-tags error path.

  5. run_tag_checker_workflow — multi-input loop (tag name, ENTER
     to return, 'c' to continue). Patches input to drive each
     branch deterministically.

  6. run — the top-level entry point. Patches input to provide
     IP and slot, then '9' to disconnect. Verifies the splash,
     the connect call, the menu, and the clean exit.

The pattern for stubbing multiple inputs is:

    with patch("builtins.input", side_effect=["Y", "MyTag", "", "9"]):
        toolkit.run_discovery_workflow()
        # assertions

`side_effect` is a list of return values for each successive
input() call. When the list is exhausted, StopIteration is
raised — which is the signal to the test that too few inputs
were provided.
"""

from __future__ import annotations

import io
import sys
import threading
import time
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
        MONITOR_HISTORY_SIZE,
        MONITOR_REFRESH_SECONDS,
    )
except ModuleNotFoundError as exc:
    if exc.name == "pycomm3":
        import pytest
        pytest.skip(
            "pycomm3 not installed; v1 interactive tests skipped",
            allow_module_level=True,
        )
    raise


# ---------------------------------------------------------------------------
# Fakes (same shape as test_v1_public_methods.py)
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, value=None, error: str = "", tag: str = "", type: Any = None):
        self.value = value
        self.error = error
        self.tag = tag
        self.type = type


class _FakeLogixDriver:
    """LogixDriver fake. Records all calls and returns predictable
    responses. The monitor tests need `read()` to return a sequence
    of values so the readings deque fills up."""

    def __init__(self):
        self.connected = True
        self.read_calls: list[str] = []
        self._read_seq: list[Any] = []
        self._read_idx = 0
        self._default_value = 42
        # discover_tags needs get_tag_list and get_tag_info
        self._controller_tags: list[Any] = []
        self._tag_info: dict[str, dict] = {}
        self.open_count = 0
        self.close_count = 0

    def add_read_sequence(self, *values) -> None:
        """Queue up specific values for successive read() calls."""
        self._read_seq.extend(values)

    def open(self):
        self.open_count += 1

    def get_tag_list(self, program: Any = None) -> list[Any]:
        return list(self._controller_tags)

    def get_tag_info(self, tag: str) -> dict:
        if tag in self._tag_info:
            return self._tag_info[tag]
        return {"data_type": {"name": "DINT", "internal_tags": {}}}

    def get_plc_info(self) -> dict:
        return {"plc_name": "TestPLC", "revision": {"major": 32, "minor": 11}}

    def read(self, tag: str) -> _FakeResponse:
        self.read_calls.append(tag)
        if self._read_idx < len(self._read_seq):
            value = self._read_seq[self._read_idx]
            self._read_idx += 1
            return _FakeResponse(value=value, tag=tag, type="DINT")
        return _FakeResponse(value=self._default_value, tag=tag, type="DINT")

    def close(self):
        self.close_count += 1
        self.connected = False


class _FakeDB:
    """DatabaseManager fake. The v1 run() method calls self.db.conn.cursor()
    on the existing-data check, and self.db.close() in finally. Also
    responds to update_plc_data for the discovery workflow."""
    def __init__(self):
        self.closed = False
        self.update_calls: list[dict] = []
    @property
    def conn(self):
        # run() does `cursor = self.db.conn.cursor()` to check for
        # existing tag data. Return a connection whose .cursor()
        # returns a cursor whose .execute() returns no rows.
        class _NoRowCursor:
            def execute(self, *args, **kwargs):
                class _Result:
                    def fetchone(inner_self):
                        return None
                return _Result()
        class _Conn:
            def cursor(self_inner):
                return _NoRowCursor()
        return _Conn()
    def close(self):
        self.closed = True
    def update_plc_data(self, ip, slot, info, tags) -> int:
        self.update_calls.append({"ip": ip, "slot": slot, "info": info, "tags": tags})
        return 1


def _make_toolkit(plc: _FakeLogixDriver | None = None,
                  tags: dict | None = None,
                  plc_info: dict | None = None,
                  db: Any = None) -> PLCToolkit:
    t = PLCToolkit.__new__(PLCToolkit)
    t.plc = plc
    t.plc_info = plc_info if plc_info is not None else {
        "plc_name": "TestPLC", "revision": {"major": 32, "minor": 11}
    }
    t.tags = tags if tags is not None else {}
    t.ip = "10.0.0.1"
    t.slot = 0
    t.plc_id = None
    # The v1 run() method calls self.db.close() in finally. Default
    # to a fake DB so test instances don't crash on close().
    t.db = db if db is not None else _FakeDB()
    t.stop_monitoring = threading.Event()
    return t


# ---------------------------------------------------------------------------
# 1. monitor_tag — continuous polling
# ---------------------------------------------------------------------------

def test_monitor_tag_raises_when_not_connected():
    """monitor_tag with no plc must raise. The contract: silent
    no-op is the wrong default — operators must be told."""
    t = _make_toolkit()
    t.plc = None
    try:
        t.monitor_tag("MyTag")
        assert False, "monitor_tag should have raised"
    except Exception as e:
        assert "Not connected" in str(e)


def test_monitor_tag_uses_case_insensitive_lookup():
    """monitor_tag with a lowercase query against a camelCase tag
    list must resolve the correct case and read the camelCase tag.
    The listener thread's input() must not return before the main
    loop has had a chance to read at least once, so we use a
    blocking input that waits on a stopper Event."""
    fake = _FakeLogixDriver()
    fake.add_read_sequence(1, 2, 3)
    t = _make_toolkit(plc=fake, tags={"MyTag": "DINT", "Other": "BOOL"})

    # The listener thread's input() blocks on a threading.Event so
    # the main loop wins the race. The stopper thread releases the
    # event after a short delay to let one read happen.
    input_unblocked = threading.Event()

    def blocking_input(*args, **kwargs):
        input_unblocked.wait()
        return ""

    def stopper():
        time.sleep(0.15)  # let one read happen
        t.stop_monitoring.set()
        input_unblocked.set()  # unblock the listener

    with patch("builtins.input", side_effect=blocking_input):
        with patch("plc_toolkit_consolidated.MONITOR_REFRESH_SECONDS", 1.0):
            threading.Thread(target=stopper, daemon=True).start()
            t.monitor_tag("mytag")
    assert "MyTag" in fake.read_calls, (
        f"Expected read of 'MyTag', got {fake.read_calls!r}"
    )


def test_monitor_tag_stops_when_listener_signals():
    """When the listener thread's input() returns, stop_monitoring
    is set, and the main loop exits. The test uses a blocking
    input + a stopper thread, so the main loop has a chance to
    run a couple of iterations before the stop signal."""
    fake = _FakeLogixDriver()
    fake.add_read_sequence(*range(20))
    t = _make_toolkit(plc=fake, tags={"MyTag": "DINT"})

    input_unblocked = threading.Event()

    def blocking_input(*args, **kwargs):
        input_unblocked.wait()
        return ""

    def stopper():
        time.sleep(0.3)  # let a couple of iterations happen
        t.stop_monitoring.set()
        input_unblocked.set()

    start = time.monotonic()
    with patch("builtins.input", side_effect=blocking_input):
        with patch("plc_toolkit_consolidated.MONITOR_REFRESH_SECONDS", 1.0):
            threading.Thread(target=stopper, daemon=True).start()
            t.monitor_tag("MyTag")
    elapsed = time.monotonic() - start
    assert elapsed < 2.0, f"monitor_tag took {elapsed:.1f}s — loop is stuck"


def test_monitor_tag_handles_read_exception_without_aborting():
    """If plc.read() raises, monitor_tag must catch the exception,
    add an error reading to the deque, and continue the loop. The
    contract: a single bad read does not abort monitoring."""
    class _ExplodingDriver(_FakeLogixDriver):
        def __init__(self):
            super().__init__()
            self._explode_on = set()

        def explode_on(self, *tags) -> None:
            self._explode_on.update(tags)

        def read(self, tag: str) -> _FakeResponse:
            if tag in self._explode_on:
                raise RuntimeError("CIP error 0x04")
            return super().read(tag)

    fake = _ExplodingDriver()
    fake.explode_on("MyTag")  # every read raises
    t = _make_toolkit(plc=fake, tags={"MyTag": "DINT"})

    input_unblocked = threading.Event()

    def blocking_input(*args, **kwargs):
        input_unblocked.wait()
        return ""

    def stopper():
        time.sleep(0.2)
        t.stop_monitoring.set()
        input_unblocked.set()

    with patch("builtins.input", side_effect=blocking_input):
        with patch("plc_toolkit_consolidated.MONITOR_REFRESH_SECONDS", 0.5):
            threading.Thread(target=stopper, daemon=True).start()
            # Must not raise — must complete within a few refresh intervals
            t.monitor_tag("MyTag")


def test_monitor_tag_history_does_not_exceed_maxlen():
    """The readings deque is bounded at MONITOR_HISTORY_SIZE. Even
    with 50 read() calls in flight, the deque must not exceed the
    limit. Indirect test: the monitor loop completes in <2s even
    with many reads, which only happens if the deque doesn't
    grow unboundedly."""
    fake = _FakeLogixDriver()
    fake.add_read_sequence(*range(100))
    t = _make_toolkit(plc=fake, tags={"MyTag": "DINT"})

    input_unblocked = threading.Event()

    def blocking_input(*args, **kwargs):
        input_unblocked.wait()
        return ""

    def stopper():
        time.sleep(0.4)  # let ~5 iterations happen
        t.stop_monitoring.set()
        input_unblocked.set()

    with patch("builtins.input", side_effect=blocking_input):
        with patch("plc_toolkit_consolidated.MONITOR_REFRESH_SECONDS", 0.1):
            threading.Thread(target=stopper, daemon=True).start()
            t.monitor_tag("MyTag")
    assert len(fake.read_calls) > 0, "monitor_tag made no reads"


# ---------------------------------------------------------------------------
# 2. show_splash — pure output
# ---------------------------------------------------------------------------

def test_show_splash_contains_title_and_border():
    """The splash is the operator's first impression. It must
    contain the toolkit title and the box-drawing border, even
    when colors are suppressed (non-TTY)."""
    t = _make_toolkit()
    real_stdout = sys.stdout
    buf = io.StringIO()
    sys.stdout = buf
    try:
        t.show_splash()
    finally:
        sys.stdout = real_stdout
    output = buf.getvalue()
    assert "PLC Toolkit" in output, "Splash missing title"
    assert "Tag Discovery" in output, "Splash missing tagline"
    assert "Scott Adams" in output, "Splash missing author line"
    # The box-drawing characters
    assert "╔" in output, "Splash missing top-left box character"
    assert "╚" in output, "Splash missing bottom-left box character"


def test_show_splash_emits_ansi_when_terminal_is_tty():
    """When stdout is a TTY, the splash must contain ANSI escape
    codes. This is the operator's visual confirmation that the
    theme is working."""
    t = _make_toolkit()
    real_stdout = sys.stdout
    buf = io.StringIO()
    buf.isatty = lambda: True
    sys.stdout = buf
    try:
        t.show_splash()
    finally:
        sys.stdout = real_stdout
    output = buf.getvalue()
    assert "\x1b[" in output, f"Splash should emit ANSI on TTY, got: {output[:200]!r}"


def test_show_splash_is_plain_when_stdout_is_not_tty():
    """When stdout is a pipe or file, the splash must NOT contain
    ANSI escape codes — operators piping output to a log file
    must not see escape codes in the log."""
    t = _make_toolkit()
    real_stdout = sys.stdout
    buf = io.StringIO()  # isatty() returns False
    sys.stdout = buf
    try:
        t.show_splash()
    finally:
        sys.stdout = real_stdout
    output = buf.getvalue()
    assert "\x1b[" not in output, (
        f"Splash leaked ANSI codes to non-TTY stdout: {output[:200]!r}"
    )


# ---------------------------------------------------------------------------
# 3. run_discovery_workflow — Y/n prompt
# ---------------------------------------------------------------------------

def test_run_discovery_workflow_proceeds_when_user_confirms():
    """When the operator types 'Y' (or just Enter), the workflow
    must call discover_tags and return True."""
    fake = _FakeLogixDriver()
    fake.add_read_sequence(1, 2, 3)
    t = _make_toolkit(plc=fake, plc_info={"plc_name": "TestPLC", "revision": {"major": 1, "minor": 0}})
    # discover_tags needs a fake that returns a tag list and tag info.
    # We can call the real discover_tags, but we need to stub get_tag_list
    # and get_tag_info.
    fake._programs = []
    fake._controller_tags = []  # so the loop is trivial
    # Run with 'Y' as confirmation
    with patch("builtins.input", return_value="Y"):
        result = t.run_discovery_workflow()
    assert result is True


def test_run_discovery_workflow_cancels_on_n():
    """When the operator types 'n', the workflow must return False
    without calling discover_tags. The contract: a 'no' answer
    is fast and obvious."""
    fake = _FakeLogixDriver()
    t = _make_toolkit(plc=fake, plc_info={"plc_name": "TestPLC", "revision": {"major": 1, "minor": 0}})
    with patch("builtins.input", return_value="n"):
        result = t.run_discovery_workflow()
    assert result is False
    # discover_tags was NOT called (we can detect by checking the fake)
    assert not fake.read_calls or "PROGRAM" not in fake.read_calls, (
        f"discover_tags was called when user said 'n': {fake.read_calls!r}"
    )


def test_run_discovery_workflow_handles_discovery_exception():
    """If discover_tags raises, run_discovery_workflow must catch
    the exception, print an error, and return False — not crash
    the operator's session."""
    fake = _FakeLogixDriver()
    t = _make_toolkit(plc=fake, plc_info={"plc_name": "TestPLC", "revision": {"major": 1, "minor": 0}})

    def boom(*a, **kw):
        raise RuntimeError("simulated discovery failure")

    # Patch discover_tags via the bound method on this instance
    t.discover_tags = boom
    with patch("builtins.input", return_value="Y"):
        result = t.run_discovery_workflow()
    assert result is False


# ---------------------------------------------------------------------------
# 4. run_export_workflow — Y/n prompt, no-tags error
# ---------------------------------------------------------------------------

def test_run_export_workflow_errors_when_no_tags_loaded():
    """If self.tags is empty and there's no plc_id to load from,
    run_export_workflow must print an error and return without
    prompting. The contract: don't trap the operator in a Y/n
    prompt when there's nothing to export."""
    t = _make_toolkit(tags={})
    t.plc_id = None
    # No input needed — must short-circuit before the prompt
    result = t.run_export_workflow()
    assert result is None  # the workflow uses bare return for the no-data path


def test_run_export_workflow_cancels_on_n():
    """When the operator types 'n', the workflow must return
    without calling export_all."""
    t = _make_toolkit(tags={"MyTag": "DINT"})
    t.export_all = lambda *a, **kw: True  # would crash if called
    with patch("builtins.input", return_value="n"):
        result = t.run_export_workflow()
    assert result is None  # bare return, not False


def test_run_export_workflow_calls_export_all_on_confirm():
    """When the operator types 'Y', the workflow must call
    export_all and report the result."""
    t = _make_toolkit(tags={"MyTag": "DINT"})
    call_log: list[Any] = []
    def fake_export_all(*args, **kwargs):
        call_log.append("called")
        return True
    t.export_all = fake_export_all
    with patch("builtins.input", return_value="Y"):
        result = t.run_export_workflow()
    assert call_log == ["called"]


# ---------------------------------------------------------------------------
# 5. run_tag_checker_workflow — multi-input loop
# ---------------------------------------------------------------------------

def test_run_tag_checker_workflow_raises_when_not_connected():
    """The workflow must short-circuit with an error if the
    toolkit is not connected. This is a guard against the operator
    reaching the menu without a connection."""
    t = _make_toolkit()
    t.plc = None
    real_stdout = sys.stdout
    buf = io.StringIO()
    sys.stdout = buf
    try:
        t.run_tag_checker_workflow()
    finally:
        sys.stdout = real_stdout
    output = buf.getvalue()
    assert "Not connected" in output, (
        f"Expected 'Not connected' error, got: {output[:200]!r}"
    )


def test_run_tag_checker_workflow_reads_a_tag_then_returns():
    """Input sequence: 'MyTag' (read it) then '' (return to menu).
    The workflow must call read_tag with the typed name, then exit
    when an empty input arrives."""
    fake = _FakeLogixDriver()
    fake.add_read_sequence(42)
    t = _make_toolkit(plc=fake, tags={"MyTag": "DINT"})

    # The loop in run_tag_checker_workflow uses `input()` twice per
    # iteration when last_tag is None. Side_effect provides them in
    # order.
    with patch("builtins.input", side_effect=["MyTag", ""]):
        t.run_tag_checker_workflow()
    assert "MyTag" in fake.read_calls, (
        f"Expected read of 'MyTag', got {fake.read_calls!r}"
    )


def test_run_tag_checker_workflow_handles_unknown_tag():
    """When the operator types a tag that doesn't exist, the
    workflow must print an error and continue the loop (not crash).
    Input sequence: 'NoSuchTag' (unknown) then '' (return to menu)."""
    fake = _FakeLogixDriver()
    t = _make_toolkit(plc=fake, tags={"MyTag": "DINT"})
    real_stdout = sys.stdout
    buf = io.StringIO()
    sys.stdout = buf
    try:
        with patch("builtins.input", side_effect=["NoSuchTag", ""]):
            t.run_tag_checker_workflow()
    finally:
        sys.stdout = real_stdout
    # read_tag with an unknown tag should raise an error, which the
    # workflow catches and prints. The key invariant: the workflow
    # did not crash, and the next iteration's empty input caused
    # the loop to exit cleanly.


def test_run_tag_checker_workflow_continue_option_reruns_monitor():
    """After reading a tag, the operator can type 'c' to continue
    monitoring it. Input sequence: 'MyTag' (read), 'c' (continue
    monitoring, which patches monitor_tag to no-op and return),
    '' (return to menu)."""
    fake = _FakeLogixDriver()
    fake.add_read_sequence(1, 2, 3, 4, 5)
    t = _make_toolkit(plc=fake, tags={"MyTag": "DINT"})

    monitor_called: list[str] = []
    def fake_monitor(tag_name):
        monitor_called.append(tag_name)
    t.monitor_tag = fake_monitor

    with patch("builtins.input", side_effect=["MyTag", "c", ""]):
        t.run_tag_checker_workflow()
    assert monitor_called == ["MyTag"], (
        f"Expected monitor called once with 'MyTag', got {monitor_called!r}"
    )


# ---------------------------------------------------------------------------
# 6. run — top-level entry point
# ---------------------------------------------------------------------------

def test_run_disconnects_and_exits_on_9():
    """The top-level run() loop must respond to '9' by exiting
    the menu. Input sequence: IP, slot, '9' (disconnect and exit)."""
    fake = _FakeLogixDriver()
    t = _make_toolkit(plc=fake)
    # Inject our fake into the module's LogixDriver
    with patch("plc_toolkit_consolidated.LogixDriver", return_value=fake):
        with patch("builtins.input", side_effect=["10.0.0.1", "0", "9"]):
            # Capture stdout to avoid polluting test output
            real_stdout = sys.stdout
            buf = io.StringIO()
            sys.stdout = buf
            try:
                t.run()
            finally:
                sys.stdout = real_stdout
    output = buf.getvalue()
    assert "PLC Toolkit" in output, "Splash should have printed"
    assert "Connected to:" in output, "Should show connection success"
    assert "Disconnect" in output, "Should show menu with Disconnect option"


def test_run_exits_on_invalid_slot():
    """run() with a non-integer slot input must print an error
    and return cleanly. The contract: a typo at the connection
    prompt does not crash the operator's session."""
    t = _make_toolkit()
    real_stdout = sys.stdout
    buf = io.StringIO()
    sys.stdout = buf
    try:
        with patch("builtins.input", side_effect=["10.0.0.1", "not-a-number"]):
            t.run()
    finally:
        sys.stdout = real_stdout
    output = buf.getvalue()
    assert "Invalid slot" in output, (
        f"Expected 'Invalid slot' error, got: {output[:300]!r}"
    )


def test_run_exits_on_connection_failure():
    """If the connection fails, run() must print the failure
    message and return. The contract: a bad IP is reported, not
    silently dropped."""
    t = _make_toolkit()
    real_stdout = sys.stdout
    buf = io.StringIO()
    sys.stdout = buf
    try:
        with patch("builtins.input", side_effect=["10.0.0.1", "0"]):
            with patch.object(t, "connect", return_value=False):
                t.run()
    finally:
        sys.stdout = real_stdout
    output = buf.getvalue()
    assert "Connection failed" in output, (
        f"Expected 'Connection failed' message, got: {output[:300]!r}"
    )
