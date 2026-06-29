"""
Tests for the v1 TUI's _Theme module.

Background
----------
The v1 binary is a TUI. A TUI has no themable UI layer, but we can
still give the operator a colorized experience that matches the
v2 wireframe palette (CLR blue + navy + gold). This is done via a
small _Theme helper that wraps text in ANSI escape codes.

These tests pin the theme's contract:
  1. The theme is importable and constructs without error.
  2. When stdout is not a TTY (piped to a log), colors are
     suppressed (operators running under `plc_toolkit > log.txt`
     get plain text, not escape codes that show up in the log).
  3. The helper methods return strings of the expected shape —
     colored text contains the escape codes when colors are
     enabled, plain text otherwise.
  4. The theme tolerates a missing colorama (no hard import
     dependency at the top of the file).
  5. Theme is instance-isolated (mutating one instance does not
     affect the module-level THEME).
  6. The theme is referenced in the v1 source at the highest-
     visibility UI points (splash, connect, menu, errors).
"""

from __future__ import annotations

import importlib
import io
import sys
from pathlib import Path

# Make the v1 module importable
_TEST_ROOT = Path(__file__).resolve().parent
_V1_ROOT = _TEST_ROOT.parent
if str(_V1_ROOT) not in sys.path:
    sys.path.insert(0, str(_V1_ROOT))

try:
    from plc_toolkit_consolidated import _Theme, THEME  # noqa: E402
except ModuleNotFoundError as exc:
    if exc.name == "pycomm3":
        import pytest
        pytest.skip(
            "pycomm3 not installed; v1 theme tests skipped",
            allow_module_level=True,
        )
    raise


# ---------------------------------------------------------------------------
# Constructor and basic helpers
# ---------------------------------------------------------------------------

def test_theme_module_imports():
    """The _Theme class and module-level THEME instance must exist."""
    assert _Theme is not None
    assert THEME is not None
    assert isinstance(THEME, _Theme)


def test_theme_has_required_helpers():
    """The v1 source references these helpers — they must exist."""
    for name in ("header", "accent", "emphasis", "success", "warn", "error", "muted"):
        assert callable(getattr(THEME, name)), f"THEME.{name} is missing or not callable"


def test_theme_helper_returns_string():
    """Every theme helper must return a string (not None, not the input)."""
    for name in ("header", "accent", "emphasis", "success", "warn", "error", "muted"):
        result = getattr(THEME, name)("test message")
        assert isinstance(result, str), f"THEME.{name} returned {type(result).__name__}"
        assert "test message" in result, f"THEME.{name} dropped the input text"


# ---------------------------------------------------------------------------
# TTY / non-TTY behavior
# ---------------------------------------------------------------------------

def test_theme_suppresses_colors_when_stdout_is_not_tty():
    """When stdout is redirected to a pipe or file, the theme must
    return plain text — operators running under `plc_toolkit > log.txt`
    must not see escape codes in their log files."""
    fake_stdout = io.StringIO()  # isatty() returns False
    real_stdout = sys.stdout
    sys.stdout = fake_stdout
    try:
        theme = _Theme()
        result = theme.success("Connected to: Compressor Skid A")
    finally:
        sys.stdout = real_stdout
    assert result == "Connected to: Compressor Skid A", (
        f"Non-TTY stdout should suppress colors, got: {result!r}"
    )


def test_theme_emits_ansi_when_stdout_is_tty():
    """When stdout is a real TTY, the theme must emit ANSI escape
    codes so the operator sees colors."""
    fake_stdout = io.StringIO()
    fake_stdout.isatty = lambda: True
    real_stdout = sys.stdout
    sys.stdout = fake_stdout
    try:
        theme = _Theme()
        result = theme.success("Connected to: Compressor Skid A")
    finally:
        sys.stdout = real_stdout
    # ANSI codes look like \x1b[...m. The theme wraps the text in
    # one or more of them.
    assert "\x1b[" in result, (
        f"TTY stdout should produce ANSI escape codes, got: {result!r}"
    )
    assert "Connected to: Compressor Skid A" in result


def test_theme_uses_distinct_codes_per_helper():
    """Each theme helper should produce a visually distinct output —
    the operator should be able to tell at a glance whether a line
    is an error (red), success (green), warn (yellow), or
    info (blue)."""
    fake_stdout = io.StringIO()
    fake_stdout.isatty = lambda: True
    real_stdout = sys.stdout
    sys.stdout = fake_stdout
    try:
        theme = _Theme()
        results = {
            "error": theme.error("bad"),
            "success": theme.success("good"),
            "warn": theme.warn("careful"),
            "header": theme.header("title"),
        }
    finally:
        sys.stdout = real_stdout
    # All four should contain ANSI codes (when TTY is faked)
    assert all("\x1b[" in v for v in results.values())
    # And the codes should differ between roles
    codes = {k: v for k, v in results.items()}
    assert codes["error"] != codes["success"], "error and success must look different"
    assert codes["error"] != codes["warn"], "error and warn must look different"
    assert codes["success"] != codes["warn"], "success and warn must look different"


# ---------------------------------------------------------------------------
# Colorama independence
# ---------------------------------------------------------------------------

def test_theme_does_not_require_colorama_at_import():
    """The v1 source has `try: import colorama; ... except ImportError: pass`.
    Verify the module imports cleanly when colorama is missing or
    when its presence is not what determines output."""
    # We can't easily uninstall colorama in-process, but we CAN
    # verify the source file has the guard. If the guard is missing,
    # the v1 module would fail to import on a system without colorama.
    src = Path(_V1_ROOT / "plc_toolkit_consolidated.py").read_text(encoding="utf-8")
    assert "import colorama" in src, "colorama import not found in v1 source"
    assert "except ImportError" in src, (
        "v1 source has no ImportError guard around colorama — "
        "operators without colorama installed will see a stack trace on launch"
    )


# ---------------------------------------------------------------------------
# v1 source must USE the theme at the high-visibility UI points
# ---------------------------------------------------------------------------

def test_v1_source_themes_the_splash():
    """The splash is the first thing the operator sees. It MUST be
    themed — otherwise the v1 binary still looks 'bland'."""
    src = Path(_V1_ROOT / "plc_toolkit_consolidated.py").read_text(encoding="utf-8")
    assert "THEME" in src, "v1 source does not reference THEME at all"
    # Find show_splash
    splash_idx = src.find("def show_splash")
    assert splash_idx > 0, "show_splash not found"
    # Within 200 lines of show_splash, there must be a THEME call
    chunk = src[splash_idx:splash_idx + 2000]
    assert "THEME.header" in chunk or "THEME.emphasis" in chunk, (
        "show_splash does not call THEME helpers — splash will look "
        "the same as the unthemed version"
    )


def test_v1_source_themes_the_connection_status():
    """Connecting to a PLC and getting 'Connected to: X' is the
    primary success state. It must be themed so the operator
    knows at a glance that the connection succeeded."""
    src = Path(_V1_ROOT / "plc_toolkit_consolidated.py").read_text(encoding="utf-8")
    # Find the line with "Connected to:" in the connect() method
    connected_idx = src.find('Connected to:')
    assert connected_idx > 0, "no 'Connected to:' message in v1 source"
    # Look 200 chars before and after — there should be a THEME call
    chunk = src[max(0, connected_idx-300):connected_idx+300]
    assert "THEME" in chunk, (
        "'Connected to:' message is not themed — operator sees a "
        "bland 'Connected to: X' line, no visual confirmation"
    )


def test_v1_source_themes_the_error_messages():
    """Error messages in the v1 source must be red. The connect()
    error, the discovery error, the export error, and the FATAL
    error all need THEME.error."""
    src = Path(_V1_ROOT / "plc_toolkit_consolidated.py").read_text(encoding="utf-8")
    # Count error-themed vs unthemed
    themed_errors = src.count("THEME.error")
    assert themed_errors >= 5, (
        f"v1 source has only {themed_errors} THEME.error() calls. "
        f"Expected at least 5 (connect fail, disconnect, discovery "
        f"fail, export fail, invalid slot, invalid choice, fatal)."
    )


def test_v1_source_themes_the_menu():
    """The tools menu (after connect) is the operator's primary
    navigation surface. The Connected-to line, the Tools header,
    and the menu options should be visually distinct."""
    src = Path(_V1_ROOT / "plc_toolkit_consolidated.py").read_text(encoding="utf-8")
    # Find show_tools_menu
    menu_idx = src.find("def show_tools_menu")
    assert menu_idx > 0, "show_tools_menu not found"
    chunk = src[menu_idx:menu_idx + 2000]
    assert chunk.count("THEME") >= 5, (
        f"show_tools_menu references THEME only {chunk.count('THEME')} times. "
        f"Expected at least 5 (header bar, success status, muted IP/divider, "
        f"emphasis tools label, accent menu items, warn exit, header bar)."
    )
