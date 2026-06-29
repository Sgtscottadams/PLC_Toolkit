"""
Behavioral tests for the v1 binary's discover_tags method.

Background
----------
The v1 binary (plc_toolkit_consolidated.py) ships to operators as
PLC_Toolkit.exe. A real bug, reported in production: opening the tag
browser against a CompactLogix that accepts the TCP/44818 connection
but stalls on `get_tag_list(program=...)` for any program causes
discover_tags to hang indefinitely with no visible progress and no
way to abort. Operator hits Ctrl+C, terminal looks frozen.

Root cause
----------
`discover_tags` has no total wall-clock budget and no per-program
timeout. Each `self.plc.get_tag_list(program=prog_name)` call uses the
LogixDriver constructor's socket timeout (10s) but loops over every
program the PLC claims to have. A PLC with 30 programs where 5 of them
stall yields 5x10s of apparent hang. Worse, the inner
`except Exception: pass` silently swallows per-program failures, so
the operator gets no diagnostic.

Contract pinned by these tests
------------------------------
discover_tags MUST:

  1. Return within a configurable total wall-clock budget, regardless
     of how many programs the PLC reports.
  2. Cap each per-program call so a single bad program cannot blow
     the entire budget.
  3. Emit a real, operator-visible warning for every skipped program
     (replacing the silent `except Exception: pass`).
  4. Still return controller-scoped tags even when the per-program
     loop is aborted early.

The tests import the real v1 `PLCToolkit` from
`plc_toolkit_consolidated` and inject a fake PLC driver by setting
`toolkit.plc` directly (skipping `connect()` which would touch the
real LogixDriver). The fake uses an interruptible busy loop (not
`time.sleep`) because pure Python cannot interrupt a sleeping thread;
real pycomm3 socket I/O *is* interruptible at the OS level via socket
timeouts. The fake mirrors that property so the test exercises the
same code path the production fix will run.

These tests are RED against the unpatched v1 source (which doesn't
accept `timeout` or `per_program_timeout` parameters) and turn GREEN
once the production fix lands.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any

# Make the v1 module importable from ab_poller/ root regardless of
# where pytest is invoked from.
_HERE = Path(__file__).resolve().parent
_V1_ROOT = _HERE.parent
if str(_V1_ROOT) not in sys.path:
    sys.path.insert(0, str(_V1_ROOT))

# Importing the v1 module triggers the import of `pycomm3.LogixDriver`
# at module top. If pycomm3 is not installed, skip the suite with a
# clear message rather than failing on import.
try:
    from plc_toolkit_consolidated import PLCToolkit  # noqa: E402
except ModuleNotFoundError as exc:
    if exc.name == "pycomm3":
        import pytest
        pytest.skip(
            "pycomm3 not installed; v1 discover_tags tests skipped",
            allow_module_level=True,
        )
    raise


# ---------------------------------------------------------------------------
# Interruptible stall simulation. Mirrors what a real pycomm3 socket
# timeout looks like to a worker thread: the call wakes up promptly
# when cancelled, instead of holding the thread hostage in time.sleep.
# ---------------------------------------------------------------------------

class _SimulatedSocketTimeout(Exception):
    """Stand-in for socket.timeout. Production pycomm3 raises this when
    the LogixDriver's constructor-level `timeout` elapses."""


def _interruptible_stall(seconds: float, cancelled: threading.Event) -> None:
    """Sleep `seconds` but return early if `cancelled` is set. Polls at
    50ms so cancellation latency is bounded."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cancelled.is_set():
            raise _SimulatedSocketTimeout()
        time.sleep(min(0.05, end - time.monotonic()))


# ---------------------------------------------------------------------------
# Stand-in for pycomm3.LogixDriver. Mirrors the shape
# plc_toolkit_consolidated.discover_tags relies on.
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, value: Any, error: str = "") -> None:
        self.value = value
        self.error = error


class _FakeTagSummary(dict):
    """Behaves like both a dict and an attribute-access object. The v1
    code uses both shapes depending on whether `data_type` came back
    as a dict or an object with a `.name` attribute (see line 262)."""

    def __init__(self, name: str, data_type: Any = "DINT") -> None:
        super().__init__(tag_name=name, data_type=data_type)
        self.tag_name = name
        self.data_type = data_type


class _FakeLogixDriver:
    """LogixDriver fake that simulates the production hang.

    `get_tag_list(program=...)` blocks for `program_stall_seconds` and
    respects a cooperative cancellation event, so the thread returns
    promptly when the production fix cancels the call after its
    budget elapses. The fake mirrors real pycomm3 behavior: a socket
    timeout is interruptible, not a `time.sleep` prison.
    """

    def __init__(
        self,
        controller_tags: list[_FakeTagSummary] | None = None,
        programs: list[str] | None = None,
        program_stall_seconds: float = 0.0,
        per_program_results: dict[str, list[_FakeTagSummary]] | None = None,
    ) -> None:
        self.connected = True
        self._controller_tags = controller_tags or []
        self._programs = programs or []
        self._program_stall = program_stall_seconds
        self._per_program_results = per_program_results or {}
        self._cancelled_event = threading.Event()
        self._cancelled_programs: list[str] = []

    def get_tag_list(self, program: str | None = None) -> list[_FakeTagSummary]:
        if program is None:
            return self._controller_tags
        try:
            if self._program_stall > 0:
                _interruptible_stall(self._program_stall, self._cancelled_event)
        except _SimulatedSocketTimeout:
            self._cancelled_programs.append(program)
            raise
        return self._per_program_results.get(program, [])

    def read(self, tag: str) -> _FakeResponse:
        if tag == "PROGRAM":
            return _FakeResponse(value=self._programs)
        return _FakeResponse(value=None, error=f"Unknown tag {tag}")

    def get_tag_info(self, tag: str) -> dict:
        return {"data_type": {"name": "DINT", "internal_tags": {}}}

    def close(self) -> None:
        self.connected = False


def _make_toolkit_with_fake_plc(
    controller_tags: list[_FakeTagSummary] | None = None,
    programs: list[str] | None = None,
    program_stall_seconds: float = 0.0,
    per_program_results: dict[str, list[_FakeTagSummary]] | None = None,
    plc: _FakeLogixDriver | None = None,
) -> tuple[PLCToolkit, _FakeLogixDriver]:
    """Build a PLCToolkit whose `self.plc` is a fake. Does not call
    connect() — that would touch the real LogixDriver. The fake is
    attached directly."""
    toolkit = PLCToolkit.__new__(PLCToolkit)
    if plc is None:
        plc = _FakeLogixDriver(
            controller_tags=controller_tags,
            programs=programs,
            program_stall_seconds=program_stall_seconds,
            per_program_results=per_program_results,
        )
    toolkit.plc = plc
    toolkit.plc_info = {
        "plc_name": "FakePLC",
        "revision": {"major": 1, "minor": 2},
    }
    toolkit.tags = {}
    toolkit.ip = "192.0.2.10"
    toolkit.slot = 0
    toolkit.plc_id = None
    toolkit.db = None  # discover_tags does not touch the DB
    toolkit.stop_monitoring = threading.Event()
    return toolkit, plc


# ---------------------------------------------------------------------------
# Tests against the real v1 discover_tags.
# These FAIL on the unpatched v1 source (no timeout budget, no params)
# and pass once the production fix lands.
# ---------------------------------------------------------------------------

def test_discover_accepts_timeout_parameters():
    """The fix MUST add `timeout` and `per_program_timeout` parameters
    to discover_tags. Without them, operators cannot bound the wall-
    clock cost of a tag-browser session against a misbehaving PLC."""
    toolkit, _ = _make_toolkit_with_fake_plc(
        controller_tags=[_FakeTagSummary("ControllerTag")],
        programs=[],
    )

    # This will raise TypeError on the unpatched v1 source because
    # `discover_tags(self)` does not accept these kwargs.
    tags, warnings = toolkit.discover_tags(timeout=10.0, per_program_timeout=2.0)

    assert "ControllerTag" in tags


def test_discover_returns_within_total_budget_when_programs_stall():
    """A PLC that stalls 30s on every per-program call MUST NOT cause
    discover_tags to exceed the wall-clock budget. The v1 source has
    no budget — this test pins the fix."""
    toolkit, plc = _make_toolkit_with_fake_plc(
        controller_tags=[_FakeTagSummary("ControllerTag")],
        programs=["ProgA", "ProgB", "ProgC"],
        program_stall_seconds=30.0,
    )

    t0 = time.monotonic()
    tags, warnings = toolkit.discover_tags(timeout=10.0, per_program_timeout=1.0)
    elapsed = time.monotonic() - t0

    assert elapsed < 6.0, (
        f"discover_tags took {elapsed:.1f}s with a 10s total budget "
        f"and 1s per-program timeout; the timeout is not being "
        f"honored. Bug class: discover_tags hangs on a stalling PLC. "
        f"This is the production freeze."
    )
    assert "ControllerTag" in tags, (
        "Controller-scoped tags must still be returned even when the "
        "per-program call stalls. Operators lose all data otherwise."
    )
    assert len(warnings) >= 3, (
        f"Expected at least 3 warnings (one per stalling program); "
        f"got {warnings!r}. The v1 fix must surface skipped programs."
    )


def test_discover_warns_and_returns_partial_when_total_budget_hit():
    """A PLC with many programs and a tight total budget must return
    a partial result with an explicit 'budget exhausted' indicator,
    not silently drop remaining programs."""
    toolkit, plc = _make_toolkit_with_fake_plc(
        controller_tags=[_FakeTagSummary("ControllerTag")],
        programs=[f"Prog{i}" for i in range(10)],
        program_stall_seconds=10.0,
    )

    t0 = time.monotonic()
    tags, warnings = toolkit.discover_tags(timeout=2.0, per_program_timeout=1.5)
    elapsed = time.monotonic() - t0

    assert elapsed < 5.0, (
        f"discover_tags took {elapsed:.1f}s; the 2s total budget is "
        f"not being enforced. Bug class: total hang when many programs "
        f"each take the full per-program window."
    )
    # Operator visibility: the v1 fix must surface partial results
    # via the warnings list.
    assert len(warnings) > 0, (
        f"Budget was clearly hit (10 programs, 2s budget, 10s stall) "
        f"but no warnings were emitted. The v1 fix must surface the "
        f"partial result. Got warnings: {warnings!r}"
    )
    assert any("budget" in w.lower() for w in warnings) or len(warnings) >= 3, (
        f"Expected a budget-exhausted warning OR many per-program "
        f"warnings. Got: {warnings!r}"
    )


def test_discover_continues_when_one_program_fails_with_exception():
    """A program that raises (not stalls) must not abort the entire
    loop. The v1 `except Exception: pass` hides this; the fix must
    surface it and continue with the next program."""
    class _ExplodingDriver(_FakeLogixDriver):
        def get_tag_list(self, program: str | None = None):
            if program == "BadProg":
                raise RuntimeError("CIP error 0x04")
            return super().get_tag_list(program=program)

    toolkit, _ = _make_toolkit_with_fake_plc(
        plc=_ExplodingDriver(
            controller_tags=[_FakeTagSummary("ControllerTag")],
            programs=["GoodProg", "BadProg", "GoodProg2"],
            per_program_results={
                "GoodProg": [_FakeTagSummary("Tag1")],
                "GoodProg2": [_FakeTagSummary("Tag2")],
            },
        ),
    )

    tags, warnings = toolkit.discover_tags(timeout=10.0, per_program_timeout=2.0)

    assert "Program:GoodProg.Tag1" in tags
    assert "Program:GoodProg2.Tag2" in tags
    assert any("BadProg" in w and "CIP error" in w for w in warnings), (
        f"Failed program must be named in a warning with the error. "
        f"Got: {warnings!r}"
    )


def test_discover_handles_no_programs_cleanly():
    """A controller that returns no PROGRAM tag (or an empty list)
    must yield exactly the controller-scoped tags and not hang."""
    toolkit, _ = _make_toolkit_with_fake_plc(
        controller_tags=[
            _FakeTagSummary("Tag1"),
            _FakeTagSummary("Tag2"),
        ],
        programs=[],
    )

    tags, warnings = toolkit.discover_tags(timeout=10.0, per_program_timeout=2.0)

    assert "Tag1" in tags and "Tag2" in tags
    assert warnings == [], f"Clean run should have no warnings; got {warnings!r}"


def test_discover_skips_system_and_double_underscore_tags():
    """Tags starting with `__` or `System:` are internal noise; the v1
    code already filters them, and the fix must not regress this."""
    toolkit, _ = _make_toolkit_with_fake_plc(
        controller_tags=[
            _FakeTagSummary("__ControllerInternal"),
            _FakeTagSummary("System:Clock"),
            _FakeTagSummary("RealTag"),
        ],
        programs=[],
    )

    tags, warnings = toolkit.discover_tags(timeout=10.0, per_program_timeout=2.0)

    assert "RealTag" in tags
    assert "__ControllerInternal" not in tags
    assert "System:Clock" not in tags
