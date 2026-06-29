# Legacy — original PLC Toolkit TUI (pycomm3)

This folder holds the **archived** first-generation PLC Toolkit: the
`pycomm3`-based terminal UI that shipped as `PLC_Toolkit.exe` before the
PySide6 GUI replaced it.

It is kept for reference and rollback only. **Do not add features here.**

## Contents

- `PLC_Toolkit.exe` — the original TUI binary.
- `Run_Toolkit.bat` — its launcher.
- `README.txt` — its original packaging note.
- `build_windows.py`, `PLC_Toolkit.spec`, `BUILD_FOR_WINDOWS.bat` — the
  TUI build path (PyInstaller). Paths assume the old layout; would need
  fixup to rebuild.
- `*.bak` — prior build backups.

## Source

The TUI source itself, `plc_toolkit_consolidated.py`, remains in
`../ab_poller/` so its tests (`ab_poller/tests/test_tui_*.py`) continue to
resolve it. It is frozen; the comms-library separation rules in
`../AGENTS.md` still apply (the TUI is pycomm3; the GUI is pylogix).
