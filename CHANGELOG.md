# PLC Toolkit — Changelog

All notable changes to the PLC Toolkit project are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The repo lives at `C:\Users\adamssc\OneDrive - Continental Resources\Documents\Cursor\PLC Toolkit`.

The project has two parallel surfaces:

- **Live binary** — `plc_toolkit_consolidated.py` (779 lines), compiled to
  `PLC_Toolkit.exe` via PyInstaller, launched by `Run_Toolkit.bat`. Comms via
  `pycomm3.LogixDriver` (EtherNet/IP). Live DB: `plc_data.db` (tables: `plcs`,
  `tag_data`). Exports: Excel / JSON / XML to `plc_scans/`. **The v1 live
  binary uses `pycomm3`, not `pylogix`.** The `pylogix` decision below
  applies to the v2 GUI rebuild only.
- **GUI rebuild (v2.0) — in progress.** Wireframes live in `mockups/`. The
  v2.0 architecture is being redesigned around `pylogix` (one primary
  comms library, no dual-vendoring).

---

## 2026-06-30 — Fix freeze on bit-heavy PLCs: lazy bit children in Browse tree

### Fixed (`ui/workspace_view.py`)
- Bit expansion materialized every integer word's 8–64 BOOL children up
  front, so a controller with many alarm/status words produced a massive
  QTreeWidget. Building, searching, and filtering all walked that giant
  item set, causing 15–20s searches and "Not Responding" freezes.
- The Browse tree now creates a word's BOOL bit children **lazily** — only
  when the operator expands that word (`itemExpanded` → `_on_item_expanded_lazy`).
  Unexpanded words contribute one item each, so the tree size (and search /
  filter cost) is back to pre-bit levels. Bits still appear on expand, in
  exports, and remain monitorable; bit values are derived from the word's
  already-read value when expanded. The full tag/leaf model is unchanged
  (exports unaffected).
- `tests/test_bit_lazy_tree.py` — lazy creation, no duplicate children on
  re-expand, and bit-value derivation. Tests: 178 passed, 4 skipped.
- Rebuilt `PLC_Toolkit.exe` and `dist_package/PLC_Toolkit.zip`.

---

## 2026-06-30 — Export: PLC sheet on history export, working filename template, Central time

### Fixed / Added (`plck/export.py`, Export tab wiring)
- **Filename template now actually applied.** Exports used a nickname-only
  helper and ignored the template, so `{ip}` never appeared. `export_tags`
  (and the monitor-history export) now render the template
  (`{ip}_{nickname}_{YYYY-MM-DD}_{HHmm}`) via the new `render_filename()`.
  - `{ip}` dots become dashes for a valid filename: `10.250.5.123` →
    `10-250-5-123`.
  - Blank `{nickname}` collapses cleanly (no `__`):
    `{ip}_{nickname}_{date}_{time}` → `ip_date_time`.
  - `{YYYY-MM-DD}` / `{HHmm}` are **Central** time, not Zulu.
- **Excel w/ collected history now includes the PLC device-info sheet**, so
  it matches the standard Excel export structure (PLC + Tags + History).
  Extracted a shared `_write_plc_sheet()` used by both exports.
- **Central time everywhere in exports.** The PLC sheet's timestamp
  ("Discovered At" / "Exported At") is now Central with the zone label
  (e.g. `2026-06-30 10:15:00 CDT`) instead of UTC `Z`. (Monitor history
  sample timestamps were already Central.)
- `tests/test_export_filename.py` extended (template, dashes, blank-nickname
  collapse, Central conversion, history PLC sheet). Tests: 176 passed, 4 skipped.
- Rebuilt `PLC_Toolkit.exe` and `dist_package/PLC_Toolkit.zip`.

---

## 2026-06-30 — Bit expansion: integer tags expose individual BOOL bits

### Added (`plck/discovery.py`, `plck/models.py`, Browse tab)
- Scalar integer / bit-string tags (SINT, INT, DINT, LINT and unsigned /
  BYTE/WORD/DWORD/LWORD variants) are now expanded into BOOL bit children
  named `<tag>.0 .. <tag>.N-1` (e.g. `Well_1.WELL_ALARM_WORD.0` …`.31`),
  mirroring Studio 5000 bit addressing. They appear as an expandable
  dropdown in the Browse tree and in the JSON/XML/Excel exports.
  Bit-addressable widths: SINT/USINT/BYTE=8, INT/UINT/WORD=16,
  DINT/UDINT/DWORD=32, LINT/ULINT/LWORD=64. **Arrays** of these types are
  NOT expanded (would multiply the tree 8–64x per element).
- Per-bit descriptions are NOT shown: pylogix cannot read Logix tag/bit
  comments over CIP, and (per request) no static meaning table is invented.
  Bits are unnamed BOOLs.
- Performance: the post-discovery batch read targets the integer WORD only
  (one read); each bit's value is **derived** in the UI as
  `(word >> i) & 1` — no 8–64x extra PLC reads. `TagNode.bit_index`,
  `TagNode.is_bit_word()`, and updated `leaf_names()/leaf_count()` encode
  this. A bit-expanded word is both expandable and readable/monitorable
  (the word), and each bit can be inspected/monitored on demand (pylogix
  reads `Tag.N`).
- `tests/test_bit_expansion.py` (+ updated discovery tests) cover the
  expansion, leaf semantics, and bit derivation. Tests: 172 passed, 4 skipped.
- Rebuilt `PLC_Toolkit.exe` and `dist_package/PLC_Toolkit.zip`.

---

## 2026-06-30 — Excel export: single flattened sheet (was one sheet per UDT)

### Changed (`plck/export.py`, Export tab label)
- The Excel export now writes ONE workbook with a **PLC** metadata sheet and
  a single **Tags** sheet containing every tag flattened in tree order —
  matching the JSON/XML exports. Previously it created one worksheet per
  top-level UDT/tag. The Tags sheet columns are Level, Tag (full dotted
  path), Data Type, UDT, Array, Array Dim, Write; the Level column +
  full path convey the hierarchy. Added `_walk_tree_with_depth()` and
  removed the per-sheet helpers (`_write_excel_sheet`, `_safe_sheet_name`).
- Export-tab checkbox relabeled "Excel (.xlsx) — single sheet, all tags
  tree-flattened".
- `tests/test_export_filename.py` — added a test asserting the workbook has
  exactly ['PLC','Tags'] and tags are flattened in tree order with depth.
- Rebuilt `PLC_Toolkit.exe` and `dist_package/PLC_Toolkit.zip`.

---

## 2026-06-30 — Fix Excel export extension (.excel → .xlsx)

### Fixed (`plck/export.py`)
- The Excel export ("Excel (.xlsx) — one sheet per UDT, all tags
  flattened") wrote files named `*.excel` instead of `*.xlsx`. The export
  used the format key ("excel") directly as the file extension;
  JSON/XML were correct only because their key equals their extension.
  Added `_EXT_BY_FORMAT` so "excel" maps to "xlsx". Affects all callers of
  `export_tags` (the Export tab passes no explicit filename).
- `ab_poller/tests/test_export_filename.py` — 3 tests pinning the
  `.xlsx`/`.json`/`.xml` extensions per format.
- Rebuilt `PLC_Toolkit.exe` and `dist_package/PLC_Toolkit.zip`.

---

## 2026-06-30 — App icon (PLC Toolkit / Allen-Bradley CompactLogix)

### Added (`build_windows.py`, `plc_toolkit/app.py`, assets)
- Custom application icon. Added `plc_toolkit/assets/app_icon.png` (source)
  and a multi-resolution `app_icon.ico` (16–256 px). The PyInstaller EXE
  now embeds the icon (`icon=` in the spec) so `PLC_Toolkit.exe` shows the
  logo in Explorer/taskbar, and the app sets it as the window icon at
  startup (`QApplication.setWindowIcon`). Both files are bundled as data
  for the runtime window icon.
- `Pillow` added to `requirements.txt` as a **build-time only** dependency
  (icon generation); it is not imported by the running app.
- Rebuilt `PLC_Toolkit.exe` and `dist_package/PLC_Toolkit.zip`.

---

## 2026-06-29 — Diagnostics: show Vendor and Serial (no longer "?")

### Fixed (`ui/workspace_view.py`)
- The Diagnostics **Connection summary** showed `Vendor: ?` and
  `Serial: ?` for every PLC. The summary was populated at connect time,
  *before* `get_device_info()` ran, and vendor/serial aren't stored in the
  saved-connection row — so they stayed blank. The summary is now
  refreshed after discovery completes with the live device info, so Vendor
  and Serial populate from the actual `GetDeviceProperties` response.
- Not hardcoded: pylogix maps the device's VendorID to a name (Rockwell
  Automation / Allen-Bradley for AB controllers), so other vendors will
  display their own name. Serial shows the controller's hex serial.
- Rebuilt `PLC_Toolkit.exe` and `dist_package/PLC_Toolkit.zip`.

---

## 2026-06-29 — Settings: stop wheel-scroll edits; add Restore to defaults

### Fixed (`ui/settings_dialog.py`)
- **Scroll wheel no longer changes a hovered combo/spin box.** Scrolling
  the Settings page while the cursor was over a dropdown or number field
  silently changed its value. Combo boxes and spin boxes now use
  no-scroll variants (`NoScrollComboBox`/`NoScrollSpinBox`/
  `NoScrollDoubleSpinBox`) that ignore the wheel unless the control is
  focused (clicked/tabbed into); otherwise the wheel scrolls the page.
  Focus policy changed to `StrongFocus` so hovering can't grab the wheel.

### Added (`ui/settings_dialog.py`)
- **Restore to defaults** button (bottom-left of the Settings dialog).
  Resets every field on the page to its default value (paths revert to
  app defaults; current theme preserved) after a confirmation; nothing is
  written until OK. Refactored settings load into `_apply_to_widgets()`
  so it serves both initial load and the restore action.
- Rebuilt `PLC_Toolkit.exe` and `dist_package/PLC_Toolkit.zip`.

---

## 2026-06-29 — Branded splash text + visible discovery progress dialog

### Changed (`splash.py`, `build_windows.py`)
- The bootloader splash now shows **PLC Toolkit** and **Created by Scott
  Adams** baked into the image (matching the runtime Qt splash, so there's
  no late text "pop-in"). The PNG is rendered at build time under the real
  Windows Qt platform so fonts are available (the offscreen platform has
  none, which caused the earlier tofu boxes). The bootloader keeps its
  bottom-left progress overlay (the module/file names being unpacked) as a
  subtle "it's loading" indicator, restyled small and muted.

### Added (`workspace_view.py`)
- **Discovery progress dialog.** Tag discovery can take 20–30s+, and the
  only feedback was a small banner. There is now a modal busy dialog
  ("Discovering tags") with an indeterminate progress bar that updates
  with the live status ("Connecting…", "Querying tag list…") and a
  **Cancel** button that stops discovery and returns to the Connection
  Manager. (pylogix's GetTagList is a single blocking call with no
  per-tag callback, so the bar is indeterminate rather than a percentage.)
- Rebuilt `PLC_Toolkit.exe` and `dist_package/PLC_Toolkit.zip`.

---

## 2026-06-29 — Saved list only keeps connectable devices; longer discovery timeout

### Fixed (`connection_view.py`, `workspace_view.py`)
- **An unsupported device (e.g. MicroLogix) was left in Saved connections**
  after the "not supported" warning. Now:
  - `ConnectionView._on_new_connection_accepted` skips saving outright when
    the dialog test already identified an unsupported device, and otherwise
    makes "Save && connect" actually connect.
  - `WorkspaceView._on_discovery_unsupported` now **removes** the device
    from the saved list (was: persisted it). So a MicroLogix added without
    testing is auto-removed the moment discovery identifies it. Only
    devices we can browse remain in the list.

### Changed (`workers/__init__.py`)
- **Discovery timeout floor raised to 30 s.** `DiscoveryWorker` used the
  5 s connection-timeout setting for the whole tag enumeration, so a
  slow/radio-linked PLC (e.g. 10.59.3.85) timed out with
  `Unknown error ... timed out`. Tag discovery now uses
  `max(connection_timeout, 30 s)`; the quick connection test in the New
  Connection dialog still uses the short timeout. (A persistent timeout
  still means the PLC isn't answering within 30 s — check reachability,
  slot, and firewall.)
- Rebuilt `PLC_Toolkit.exe` and `dist_package/PLC_Toolkit.zip`.

### Note — test-suite teardown
- All tests pass (164 passed, 4 skipped). On this Windows + PySide6 setup
  the pytest process can segfault during interpreter shutdown *after* the
  run completes (a known Qt teardown quirk); it does not affect the built
  exe or any test result.

---

## 2026-06-29 — Fix stuck bootloader splash + tofu boxes

### Fixed (`plc_toolkit/app.py`, `plc_toolkit/splash.py`, `build_windows.py`)
- **Splash stayed on top forever** (couldn't move/close, even with the
  main window open). A PyInstaller onefile bootloader splash must be
  dismissed by the app via `pyi_splash.close()`; we never called it, so it
  persisted for the whole session. `app.main()` now closes it during
  startup (guarded import; no-op outside the frozen build).
- **Tofu boxes in the splash image.** `splash.png` is rendered at build
  time under the headless 'offscreen' Qt platform, which has no fonts, so
  the baked "PLC Toolkit"/"Loading" text became boxes. `splash_pixmap()`
  gained a `with_text` flag; the bootloader PNG is now **logo-only**
  (no text to tofu), while the runtime Qt splash (Windows, fonts present)
  keeps the text. Bootloader overlay text changed to plain ASCII
  ("Loading PLC Toolkit"; the unicode ellipsis is gone).
- Rebuilt `PLC_Toolkit.exe` and `dist_package/PLC_Toolkit.zip`.

---

## 2026-06-29 — Close the unsupported-device loophole on direct connect

### Changed (`workers`, `workspace_view.py`, `device_filter.py`)
- A direct/manual connection to a non-Logix Allen-Bradley device (e.g. a
  **MicroLogix**) previously fell through to tag discovery and surfaced a
  confusing `Unknown error ... timed out`. Now `DiscoveryWorker` checks
  the device identity right after `get_device_info()` and, if it is not a
  tag-readable Logix controller, emits a new `unsupported` signal instead
  of attempting discovery.
- `WorkspaceView` handles `unsupported` by showing a clear, **device-typed**
  dialog (e.g. "MicroLogix 1400 (1766-L32BWAA) is not supported by PLC
  Toolkit"), logging it to Diagnostics, persisting the discovered identity
  so the Connection Manager blocks it up-front next time, and returning to
  the Connection Manager.
- `device_filter.py`: added `describe_device_type()` (maps common non-Logix
  AB families — MicroLogix, SLC 500, PLC-5, PanelView, Stratix, PowerFlex,
  POINT/FLEX I/O — to friendly labels) and reworded
  `unsupported_device_message()` to lead with the specific device type.
- `ab_poller/tests/test_unsupported_device.py` — 6 tests covering the
  device-type description, the message wording, and the worker emitting
  `unsupported` (vs proceeding) for MicroLogix vs CompactLogix.
- Rebuilt `PLC_Toolkit.exe` and `dist_package/PLC_Toolkit.zip`.

---

## 2026-06-29 — Fix discovery crash: `'NoneType' object is not subscriptable`

### Fixed (`ab_poller/plck/pylogix_patches.py`, `ab_poller/plck/comms.py`)
- **Tag discovery crashed on field CompactLogix/ControlLogix** (seen on
  10.254.120.102 / .103) with `Could not discover tags: 'NoneType' object
  is not subscriptable`. Root cause is in pylogix 1.1.5: `GetTagList`
  always calls `_get_udt()`, which does `temp[46:]` on the UDT *template*
  service response. On controllers that reject/time out the template
  service, `_get_template_attribute()`/`_get_template()` return `None`
  and pylogix crashes the entire discovery.
- Added `plck/pylogix_patches.py`, a runtime resilience shim (installed
  once from `plck/comms.py`) that (1) coerces a `None` template payload to
  empty bytes so pylogix's existing "invalid template" branch skips just
  that UDT, and (2) wraps `_get_udt` so any residual failure degrades to
  the flat tag list — discovery now succeeds with atomic/top-level tags
  even when UDT member expansion is refused by the controller. Chose a
  local shim over a second comms library per AGENTS.md.
- `ab_poller/tests/test_pylogix_patches.py` — 5 tests pinning the None
  coercion, the `_get_udt` degrade-on-error backstop, pass-through on
  success, and idempotent install.
- Rebuilt `PLC_Toolkit.exe` and `dist_package/PLC_Toolkit.zip`.

### Note — MicroLogix / SLC are out of scope
- MicroLogix (and SLC) use PCCC, not the Logix symbolic tag database, so
  pylogix tag discovery cannot read them. This is expected: v2 targets the
  Logix family (ControlLogix / CompactLogix / Micro800), per AGENTS.md.
  Subnet discovery filters these out, and a direct connection is now
  blocked with a clear device-typed message (see the unsupported-device
  loophole entry above) instead of a discovery timeout.

---

## 2026-06-29 — Fix launch crash (Tcl splash) and double-folder extraction

### Fixed (`ab_poller/build_windows.py`)
- **Launch crash `SPLASH: could not find requirement tcl86t.dll in
  archive`.** Two bugs in the spec: `tkinter` was in `excludes` (which
  strips the Tcl/Tk the bootloader splash needs) and the onefile `EXE`
  was missing `splash.binaries`. Fixed by removing `tkinter` from
  `excludes` and adding both `splash` and `splash.binaries` to `EXE`, so
  Tcl/Tk is now bundled and the bootloader splash shows during the
  onefile unpack (immediate feedback before Python/Qt start). The app's
  own Qt splash still follows while the main window loads.
- **Double nested folder on extract.** The zip is now named
  `PLC_Toolkit.zip` and archives the package *contents* at the zip root
  (`base_dir="."`), so Windows "Extract All" yields a single
  `PLC_Toolkit\` folder with `PLC_Toolkit.exe` directly inside (was
  `PLC_Toolkit_Windows\PLC_Toolkit\PLC_Toolkit.exe`).
- Updated `BUILD_PORTABLE.bat`, `Quick_Start.txt`, and `README.md` for
  the new `dist_package/PLC_Toolkit.zip` name and single-folder extract.
- Rebuilt `PLC_Toolkit.exe` and `dist_package/PLC_Toolkit.zip`.

---

## 2026-06-29 — Portable package: clean extracted root (exe + folders only)

### Changed (`ab_poller/build_windows.py`, `ab_poller/plc_toolkit/settings_store.py`)
- The portable package now extracts to a root containing **only
  `PLC_Toolkit.exe` plus folders** (`assets/`, `data/`, `scans/`,
  `exports/`, `extras/`). Previously the root also held loose files
  (`Launch PLC Toolkit.vbs`, `Run_Toolkit.bat`, `Quick_Start.txt`,
  `MVP_PILOT.txt`, `portable.marker`).
- Optional launchers and the two guides moved into `extras/`. The
  launchers now target the exe in the parent folder and set the working
  directory to the app root so portable paths still resolve.
- `portable.marker` now lives in `data/`, not the root.
  `ensure_portable_layout()` writes/migrates the marker to `data/` and
  removes any legacy root-level marker, so the running exe no longer
  re-litters the extracted root. `_has_portable_marker()` checks
  `data/portable.marker` (with a root fallback for older deploys).
  Frozen builds still detect portable mode via `sys.frozen`, so the
  marker is informational only.
- Rebuilt `PLC_Toolkit.exe` and regenerated
  `dist_package/PLC_Toolkit_Windows.zip` with the clean layout. Tests:
  settings + startup green; full suite re-run after the change.

---

## 2026-06-29 — Strip version suffixes from file names; archive legacy TUI

Per owner request: file names no longer carry `v1`/`v2`. The product
version still shows in **Help → About** (`PLC Toolkit v2.0`) and is
tracked in this changelog; it is just not baked into file names anymore.

### Changed (file renames — the GUI is now the unsuffixed product)
- `PLC_Toolkit_v2.exe` → `PLC_Toolkit.exe` (repo root).
- `Run_Toolkit_v2.bat` → `Run_Toolkit.bat`; `Run_PLC_Toolkit_v2.bat` →
  `Run_PLC_Toolkit.bat` (title text de-versioned).
- `ab_poller/build_windows_v2.py` → `ab_poller/build_windows.py`;
  `ab_poller/PLC_Toolkit_v2.spec` → `ab_poller/PLC_Toolkit.spec`
  (PyInstaller `name='PLC_Toolkit'`).
- `ab_poller/BUILD_PORTABLE_v2.bat` → `ab_poller/BUILD_PORTABLE.bat`.
- `ab_poller/requirements-v2.txt` → `ab_poller/requirements.txt`.
- `dist_package_v2/` → `dist_package/`; inner `PLC_Toolkit_v2/` →
  `PLC_Toolkit/`; `PLC_Toolkit_v2.exe`/`Run_Toolkit_v2.bat` →
  `PLC_Toolkit.exe`/`Run_Toolkit.bat`;
  `PLC_Toolkit_v2_Windows.zip` → `PLC_Toolkit_Windows.zip`. The `.vbs`,
  `MVP_PILOT.txt`, `Quick_Start.txt`, and `portable.marker` inside the
  package were updated to the new names.
- `ab_poller/tests/test_v1_*.py` → `ab_poller/tests/test_tui_*.py`
  (4 files). They still import `plc_toolkit_consolidated` from the
  `ab_poller/` root, which is unchanged.
- All internal references in `build_windows.py`, `BUILD_PORTABLE.bat`,
  the launchers, and `ab_poller/README.md` updated to the new names.
  In-code product-version strings (`v2.0`, `v2.1`) in `app.py` (About),
  banners, and comments were intentionally left in place.

### Changed (legacy TUI archived to `legacy/`, reversible moves)
- Moved the abandoned pycomm3 TUI deliverables into `legacy/`:
  `PLC_Toolkit.exe` (old v1 binary), `Run_Toolkit.bat`, `README.txt`,
  `PLC_Toolkit.exe.bak`, plus the v1 build path
  (`ab_poller/build_windows.py` (old), `ab_poller/PLC_Toolkit.spec`
  (old), `ab_poller/BUILD_FOR_WINDOWS.bat`). The previous GUI build
  backup was moved to `legacy/PLC_Toolkit_prev_build.exe.bak`.
- `ab_poller/plc_toolkit_consolidated.py` (v1 source) was **kept in
  place** so `test_tui_*.py` still resolve it via `sys.path`.
- Removed stale PyInstaller caches (`ab_poller/build/PLC_Toolkit_v2/`,
  `ab_poller/dist/PLC_Toolkit_v2.exe`, the `build_windows_v2` pyc).

### Changed (`AGENTS.md`)
- Rewrote the "Two surfaces, two scopes" section to "Surfaces and scope":
  the GUI is the live product at `PLC_Toolkit.exe`; the pycomm3 TUI is
  archived in `legacy/`. Added a dated naming note. The comms-library
  hard rules (pylogix-only GUI, no pycomm3 mixing) are unchanged.

### Changed (`PROJECT_STATUS.md`, `ab_poller/README.md`)
- Updated summaries, launch commands, packaging paths, and the surfaces
  table to the de-versioned names and the `legacy/` archive.

### Verified
- `pytest tests/ -q` after the rename: see entry result in session notes.

---

## [Unreleased] — v1 binary

### Programming (`ab_poller/plc_toolkit_consolidated.py`)

#### Changed
- `discover_tags()` now accepts `timeout=30.0` and `per_program_timeout=5.0`
  keyword parameters, returning `(parsed_tags, warnings)` instead of a bare
  dict. Each per-program `get_tag_list(program=...)` call is wrapped in a
  `concurrent.futures.ThreadPoolExecutor` with a per-call timeout clamped
  to the smaller of `per_program_timeout` and the remaining total budget,
  so a stalling program call can never blow the overall budget. The
  per-program loop tracks a wall-clock deadline and breaks with a warning
  when the budget is exhausted. Replaces the silent
  `except Exception: pass` per-program skip (line 242) with explicit
  warnings listing the program name, the per-call timeout that elapsed,
  and the underlying exception. Discovery completes within the budget
  even against a CompactLogix that ACKs CIP requests but never returns
  a per-program tag list.
- Fixed pre-existing source-syntax error at the original line 250: the
  `sys.stdout.write(f"\rReading {total} Tags ")` line contained a raw
  CR (0x0d) character inside the f-string, which Python 3.11+ rejects
  with `SyntaxError: unterminated string literal`. Replaced with the
  proper escape sequence `\\r`. The compiled `PLC_Toolkit.exe` did not
  expose this because it was built when the tokenizer accepted the
  raw CR; the v1 source has not been compilable on modern Python
  until now.

#### Added
- `ab_poller/tests/test_v1_discover_tags.py` — 6 behavioral tests that
  import the real v1 `PLCToolkit`, inject a fake `LogixDriver` whose
  stall is interruptible (mirroring real socket-timeout behavior), and
  pin the contract: discover_tags must (a) accept the new parameters,
  (b) return within the total budget, (c) surface skipped programs via
  the warnings list, (d) preserve controller-scoped tags when the
  per-program loop is aborted, (e) continue past a per-program
  exception, (f) filter `__` and `System:` tags.
- `ab_poller/tests/test_v1_theme.py` — 11 tests for the new `_Theme`
  helper: required helpers exist, TTY vs. non-TTY behavior, distinct
  ANSI codes per role, colorama independence, and source-grep tests
  that pin the theme is applied at the splash, connection status,
  error messages, and tools menu.
- `ab_poller/tests/test_v1_public_methods.py` — 28 tests for the
  remaining public surface: `_parse_structure_def` (7 cases including
  scalar/UDT/nested/skip-`__`), `DatabaseManager` (CRUD round-trip and
  upsert), `connect`/`disconnect` (lifecycle, error path, kwargs
  pin), `read_tag` (case-insensitive lookup), `export_excel`/`json`/
  `xml` (file content validation, default output folder), and
  `_find_case_insensitive_tag` (dotted-path traversal).

#### Changed
- v1 TUI now displays the v2 wireframe palette (CLR blue + navy + gold)
  via a small `_Theme` helper at the highest-visibility UI points:
  splash, connection status, the tools menu, the discovery / export /
  tag-checker headers, success and error markers, and the new
  per-program warnings. `colorama` is a soft import — operators
  without it see plain text. Output piped to a log file is plain text
  by default (`isatty()` check on stdout).
- Module now forces `sys.stdout` / `sys.stderr` to UTF-8 at import
  time via `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`.
  Fixes a `UnicodeEncodeError: 'charmap' codec can't encode
  characters` crash under the PyInstaller-bundled `PLC_Toolkit.exe`
  on Windows, where the default `cp1252` codec cannot encode the
  box-drawing characters in the splash screen. POSIX is unaffected
  (UTF-8 is already the default). The reconfigure is wrapped in a
  `try/except` so legacy `sys.stdout` implementations (e.g. some
  embedded consoles) degrade to the default codec rather than
  crashing at import.
- `THEME._enabled` is now a `@property` that re-checks
  `sys.stdout.isatty()` on every call, rather than capturing the
  result at module-load time. This ensures the theme adapts when
  stdout is redirected after import (e.g. a test harness, a CI
  runner, or an operator piping output mid-session).

#### Added
- `ab_poller/tests/test_v1_interactive.py` — 21 tests for the v1
  binary's interactive surface: `monitor_tag` (raises when not
  connected, case-insensitive lookup, listener-driven stop,
  exception resilience, deque maxlen, 5 cases), `show_splash`
  (title/border content, ANSI-on-TTY, plain-on-pipe, 3 cases),
  `run_discovery_workflow` (Y-proceeds, n-cancels, exception
  resilience, 3 cases), `run_export_workflow` (no-tags error,
  n-cancels, Y-calls-export, 3 cases), `run_tag_checker_workflow`
  (not-connected guard, tag-read-and-return, unknown-tag resilience,
  'c'-continues-into-monitor, 4 cases), and `run` (disconnect-on-9,
  invalid-slot error, connection-failure exit, 3 cases). Tests use
  `unittest.mock.patch` with `side_effect` lists for sequential
  `input()` calls, and a `threading.Event`-gated blocking input to
  resolve the listener-vs-main-loop race in `monitor_tag`.
- `ab_poller/requirements-v2.txt` — added `colorama==0.4.6` with a
  comment explaining it's a soft import in `plc_toolkit_consolidated.py`
  (operators without it see plain text), but required for the v1
  test env so `test_v1_theme.py`'s TTY-color assertions are
  verifiable. PyInstaller bundles it into `PLC_Toolkit.exe`
  automatically.

#### Build (`ab_poller/build_windows.py`)
- Rebuilt `PLC_Toolkit.exe` (16.9 MB, onefile, console) with the new
  theme helpers, the UTF-8 stdout fix, and the `discover_tags`
  timeout-budget fix. The previous `.exe` (10.5 MB) was backed up
  to `PLC_Toolkit.exe.bak` before replacement. Smoke-tested the
  new binary: splash renders correctly with box-drawing characters,
  connection failure is reported cleanly, exit code is 0. The ANSI
  theme is gated on `stdout.isatty()` so operators piping output to
  a log file still get clean text without escape codes.

---

## [Unreleased] — v2.0 GUI rebuild

### Programming (`ab_poller/plc_toolkit/`, `ab_poller/plck/`)

#### Changed
- Users double-click **`PLC_Toolkit_v2.exe`** directly — portable folders and
  settings are created on startup (no `.bat` required). PyInstaller bootloader
  splash during onefile unpack; in-app splash while the main window loads.
  Optional `Launch PLC Toolkit.vbs` (no cmd flash) and silent `Run_Toolkit_v2.bat`.
- MVP portable package: `MVP_PILOT.txt` field checklist in deploy zip;
  README marks v1 TUI abandoned and v2 GUI as MVP field-test target.
- `build_windows_v2.py` uses a temp workpath (avoids OneDrive lock on
  `ab_poller/build/`) and falls back to existing `dist/` exe if rebuild fails.
- `build_windows_v2.py` produces a full portable folder and
  `dist_package_v2/PLC_Toolkit_v2_Windows.zip` (exe, launcher, `data/`,
  `scans/`, `exports/`, clean `settings.json`, `portable.marker`).
  `BUILD_PORTABLE_v2.bat` runs the build. `Run_Toolkit_v2.bat` sets
  `PLC_TOOLKIT_PORTABLE=1` and creates data folders before launch.
- Portable deploy: `Run_Toolkit_v2.bat` launches the frozen exe (for network
  shares); `Run_PLC_Toolkit_v2.bat` remains dev/source-only (Python +
  `ab_poller/`). `build_windows_v2.py` assembles `dist_package_v2/` with exe,
  launcher, and `Quick_Start.txt`.
- Subnet discovery filters out non-controller EtherNet/IP devices (PanelViews,
  Stratix switches, comm modules, etc.): only Logix-family CPUs with catalog
  prefixes `1756-L`, `1769-L`, `5069-L`, `2080-L`, and `2085-L` appear in
  scan results. Connect and manual **Test connection** block known unsupported
  devices when `product_name` is already known (`plck/device_filter.py`).
  The unsupported-device dialog includes **Remove from list** (no second
  confirmation).
- **About PLC Toolkit** (Help menu) credits Scott Adams as creator.
- Monitor chart stamped readings: clipboard icon inside the stamp box
  (bottom-right); **Copied** toast beside the button (no full-screen dialog).
- Checked checkboxes / table compare cells use Continental blue→gold gradient
  instead of green.
- Export tab: **Monitor watch list only** defaults formats to Excel w/
  collected history; current session / saved scan keep Excel + JSON defaults.
- Subnet discovery dialog: **Select all** / **Unselect all** for scan results.

#### Fixed
- Portable PyInstaller build bundles Continental logo, full PySide6 runtime,
  and all ``plc_toolkit`` / ``plck`` modules (``collect_all`` /
  ``collect_submodules``). Logo lives in ``plc_toolkit/assets/`` and is
  copied into the deploy zip ``assets/`` folder. Fixes missing logo, broken
  theme, and incomplete UI in ``Run_Toolkit_v2.bat`` vs dev launcher.
- Portable exe on a network share no longer uses `%APPDATA%` or other local
  paths baked into `data/settings.json`; foreign paths are ignored and rewritten
  on load. Settings save keeps storage paths under the app folder only.
- Subnet scan no longer fails when pylogix returns vendor as the string
  ``Rockwell Automation/Allen-Bradley`` instead of numeric ``1``
  (`plck/device_filter.normalize_vendor_id`).
- Connection Manager **Device ID** column shows catalog name (e.g. ``1769-L33ER``)
  instead of IP when ``product_name`` is known; DB migration repairs stale rows.
- Connection Manager **Revision** column (replaces duplicate **Product** column)
  shows firmware revision from discovery; **Device ID** remains the catalog model.
- **Device ID** shows plain-English family plus catalog (e.g.
  ``CompactLogix · 1769-L33ER``) derived from Rockwell catalog prefixes.
- Disconnect crash: coordinated worker shutdown — disconnect Qt signals before
  thread wait, session epoch guards on discovery/monitor callbacks, no
  ``terminate()`` on browse value populator, cooperative ``DiscoveryWorker.stop()``,
  inspector signal teardown, reprioritize timer stopped on disconnect.
- New PLC connect always opens the **Browse** tab (no sticky tab from the prior
  session) and clears the tag inspector until a tag is selected.
- Export tab Formats list order: Excel, Excel w/ collected history, JSON, XML.
- Default filename template `{ip}_{nickname}_{YYYY-MM-DD}_{HHmm}` in settings
  and Export tab (existing saved settings unchanged until user resets).
- Disconnect crash: stop browse value-populator and discovery workers cleanly;
  disconnect worker signals before teardown so late samples cannot touch UI.
- Browse search crash: filter reprioritize no longer destroys a running
  ``TreeValuePopulator`` thread (``QThread: Destroyed while thread is still running``).
- Monitor chart stamps grouped under numbered **Stamp 1**, **Stamp 2**, … blocks.
- Export **Excel w/ collected history** writes one `.xlsx` (Tags + History sheets only).
- Browse search **×** button: replaced invisible QLineEdit action with a
  visible sibling button inside `BrowseSearchBox`.
- Monitor chart stamps show **PLC read time** (`YYYY-MM-DD - HH:MM:SS` Central)
  per tag, not a stamp counter header.
- Browse search **×** button restyled (white on blue pill) for visibility inside
  the search field.
- Monitor / Browse charts: vertical cursor bar, all-tag hover readout, click-to-
  stamp panel below chart with per-tag timestamps (nearest sample at cursor X).
- Browse value polling prioritizes visible filtered tags and selected tags still
  showing "—"; hidden tags continue in the background.
- Portable / frozen builds default paths to `{app folder}/exports`, `{app folder}/scans`,
  `{app folder}/data/plc_data.db` (override via Settings or env vars).
- Settings dialog: full dark-theme styling (`QGroupBox`, scroll area, form
  controls) so text and backgrounds match the main app.
- Connection Manager: Continental **PLC Toolkit** brand header (logo when
  `plc_toolkit/assets/clr-logo.png` is present); per-row **Connect** button;
  double-click **Nickname** edits in-cell, double-click other columns connects.
- Browse search **×** moved inside the search field with themed styling.
- Browse tag counts aligned with Diagnostics: **nodes/leaves** with thousands
  separators; stale prior-PLC tree cleared on new discovery; filter shows
  “Showing X of Y”.
- History Compare: selecting a third scan drops the oldest checked row
  (rolling two-scan selection).
- Monitor watch list always clears on disconnect/connect (no bleed between PLCs).
- History Compare + Monitor Chart checkboxes: green/white checked state and light
  border when unchecked so they stay visible on selected (blue) rows; compare
  rolling-two logic fixed so **Compare checked scans** enables at exactly two.
- Browse tab search: comma-separated terms use OR logic with `*` wildcards per
  term (e.g. `PIT*, Facility*`); matching uses full tag paths; clearing the
  filter recursively unhides all tree nodes (fixes UDT expand after search).
- Browse tab search box: **×** clear button resets the filter in one click.
- Connection Manager: **Device ID** column (read-only, from discovery) split
  from editable **Nickname** (friendly well/facility name); `plcs.device_id`
  DB column with migration backfill.
- Monitor tab: **Chart** checkbox column + **Open chart** button (check tags to chart).
- Export tab: saved-scan dropdown inline to the right of its radio button.
- History tab: times shown as **Central** `YYYY-MM-DD - HH:MM`; Duration and Source
  columns removed; Compare checkboxes centered in the right column; **Refresh**
  replaced with **Re-scan PLC** (new discovery + history entry).
- Browse-tags dialog shows scan timestamp at top; chart hover shows exact time/value.
  Monitor +/- symbols larger, bold, centered without changing row height.
- Browse inspector **Chart history** opens a live trend chart (replaces duplicate
  read-history popup). Monitor tab adds **Chart selected…** for multi-tag charts.
- Export tab: saved-scan source uses an in-tab dropdown (no History tab hop).
- History tab: editable **Notes** column; **Compare** checkboxes (max two);
  Browse tags shows saved scan values when available.
- Scan leaf values persisted to DB after post-discovery batch read (`values_json`).
- Connection Manager **Last scan** column now shows relative time (`2h ago`,
  `Never`, etc.) from `plcs.last_scan`, populated after each successful tag
  discovery.
- READ-ONLY banner and Diagnostics summary: removed “in v2.0” suffix; message
  is now indefinite until write support ships.
- Browse tab: **Monitor** column header labeled; UDT parents no longer show
  misleading `+N` in that column; tag tree loads collapsed; all columns are
  manually resizable with content-based default widths.
- Monitor tab: **Remove** column header; remove button shows **X** (visible on
  all Windows fonts).
- Export tab: source options rewritten as exclusive radio buttons with hint
  text explaining current session vs History selection vs watch list.
- Default export folder now uses the user **Documents** path (follows OneDrive
  Known Folder Move on Windows): `Documents\PLCToolkit\exports`.
- History tab: **Browse tags…** opens a read-only tag tree for the selected
  scan; **Export selected scan…** replaces “View selected”; **Compare two
  scans…** (Ctrl+select two rows) shows added (green) / removed (red) leaf tags.
- Diagnostics connection summary: removed fixed 140px cap; box height fits all
  summary lines without internal scroll when vertical space allows.
- Subnet discovery (`plck/comms.py`): UDP ListIdentity broadcast filtered to
  the target subnet runs before concurrent direct TCP probes; per-probe timeout
  raised to 2s (radio-linked PLCs); progress reports every host `(n/total)`;
  zero-result dialog shows actionable troubleshooting steps.
- Browse tab freeze: removed per-leaf `QPushButton` widgets (text `+`/`−` in
  column 4 instead); chunked tree build with `processEvents()` every 100 nodes;
  blue discovery progress banner visible during tag enumeration.
- `SubnetScanDialog`: progress bar wired to scan fraction; Cancel scan button;
  bulk-add confirmation before inserting discovered PLCs.

#### Added
- Monitor chart: clipboard button copies all stamped readings.
- Workspace keeps Continental **PLC Toolkit** brand header while connected.
- Monitor Trend column header shows collection span (`09:15 - 14:32`; date on
  start only when first sample is from a prior day).
- Connection Manager + Monitor tab: click column headers to sort A–Z (toggle on
  repeat click); default Connection sort by IP, Monitor sort by tag name.
- Default export filename template `{ip}_{nickname}_{YYYY-MM-DD}`.
- Workspace **Tag History** tab label (renamed from History).
- Monitor tab: configurable history depth (Settings → **Monitor history depth**,
  10–8640 samples per tag); 500-tag watch-list cap; full Central timestamps on
  each sample (`YYYY-MM-DD - HH:MM:SS`).
- Export tab: **Excel w/ collected history** when source is Monitor watch list
  only — one `.xlsx` workbook with Tags + History worksheets.
- `plc_toolkit/ui/browse_search.py` — Browse search field with visible × button.
- `plck/export.py` — `export_monitor_history()` for watch-list time series.
- `plc_toolkit/ui/chart_dialog.py` — live single- and multi-tag trend charts.
- `plck/tag_display.py` — shared Type column formatting (`UDT (N)`).
- `ab_poller/tests/test_tag_display_and_values.py` — type label + values/notes DB tests.
- `plc_toolkit/ui/scan_dialogs.py` — browse-saved-scan and compare-two-scans
  dialogs for the History tab.
- `ab_poller/tests/test_scan_dialogs.py` — export path + scan compare tests.
- `plc_toolkit/settings_store.py` — persistent settings under
  `%APPDATA%\PLCToolkit\settings.json` (Connection, Polling, Storage, Export).
- `plc_toolkit/ui/settings_dialog.py` — Settings modal (File → Settings, ⚙ on
  Connection Manager).
- `plc_toolkit/ui/help_dialog.py` — MVP Help (F1 / Help menu): troubleshooting
  + glossary.
- READ-ONLY banner on workspace tabs; Export confirm dialog; Diagnostics shows
  `pylogix.PLC` and library version; tab-specific status bar messages.
- `ab_poller/build_windows_v2.py` — PyInstaller build for `PLC_Toolkit_v2.exe`.
- `ab_poller/tests/test_settings.py` — settings save/load tests.
- Updated `ab_poller/README.md` with v2 run, build, test, and pilot checklist.
- Built `PLC_Toolkit_v2.exe` at repo root via `build_windows_v2.py` (windowed, PySide6 + pylogix).

#### Changed
- Default export path uses `Documents\PLCToolkit\exports` (OneDrive-aware) when
  no custom folder is set in Settings; override still via Settings or
  `PLC_TOOLKIT_OUTDIR`.
- `DiscoveryWorker` uses configurable connection timeout from settings.

---
- Full CLR brand theme: navy backgrounds (#0B162C-#1D3559), blue accent
  (#1565C0), gold (#B8860B) for Monitor tab and warnings, blue-tinted white
  text (#E8ECF1). Status green (#43A047) preserved only for OK/running
  indicators. Replaces the generic terminal-green-on-gray palette.
- Read cadence floor raised: Monitor minimum 2s (was 1s), inspector default 5s
  (was 2s). Appropriate for radio-linked PLCs in field environments.
- Export default folder uses LOCALAPPDATA instead of Documents to avoid
  OneDrive Known Folder Move redirection.
- Browse tree loads fully collapsed by default. Expand All / Collapse All
  buttons added above the tree.
- Browse tree search supports * wildcards (e.g. PIT*, *Scale, *Eng). UDT
  parents that match the filter show all children; child matches show only
  the parent and matching child.
- Tree per-row "+" button toggles to "−" (red) when tag is in the watch list.
  Clicking "−" removes the tag from monitor and reverts the button to "+".
- Inspector "Watch Tag" button replaces the verbose "Add to monitor + go to
  tab". Tree "+" button adds without navigating; inspector button adds and
  switches to Monitor tab.
- Monitor "Type" column now populated from tag tree data types.
- Tree value column auto-fills via batch read after discovery completes.

#### Added
- `SubnetScanDialog` — dedicated popup for subnet discovery with multi-select
  batch add. Replaces the inline scan on the Connection Manager. Direct TCP
  port probes when a subnet is specified; broadcast when blank.
- `TreeValuePopulator` worker — one-shot batch read of all leaf tags (50 per
  CIP request) to populate the tree value column after discovery.
- Dead-control audit: 14 behavioral button tests covering every QPushButton
  in the app. Button inventory test reports all widget tree items found.
- `tests/test_subnet_discovery.py` — 12 tests covering CIDR parsing, IP
  filtering, discover() with mocks, dialog wiring.
- `tests/test_browse_inspector.py` — 8 tests for tree buttons, filter
  behavior, inspector wiring.
- `tests/test_inspector_card.py` — 4 tests for the redesigned inspector
  and tree value column.
- `tests/test_workspace_actions.py` — 5 tests for export, watch list
  isolation, per-row removal.
- `tests/test_dead_controls.py` — 14 behavioral + inventory tests.
- `tests/test_export_optional_dep.py` — 2 tests for lazy openpyxl import.
- `tests/test_comms_errors.py`, `tests/test_package_api.py`,
  `tests/test_discovery_types.py`, `tests/test_discovery_programs.py` —
  regression tests for earlier fixes.
- `gui-dead-control-audit` skill — codifies the behavioral testing discipline
  so every QPushButton gets a click-and-verify test before shipping.
- `scada-plc-tool-development` skill — 19 pitfalls documenting every
  hard-learned lesson from this build.
- `ab_poller/plc_toolkit/__main__.py` — added the missing module entrypoint so
  `python -m plc_toolkit` resolves to `plc_toolkit.app.main()`.
- Verified the v2 PySide6 app imports and creates a `MainWindow` against a
  scratch SQLite DB path without touching the live `plc_data.db` or any PLC.
- `PLC_TOOLKIT_OUTDIR` environment override added so tests and smoke runs can
  use a scratch export directory instead of creating files under the real user
  Documents path.
- Fixed PLC worker thread ownership: Discovery, Monitor, Inspector, and subnet
  discovery workers now construct `PLCClient` inside their own worker thread
  instead of receiving a UI-thread pylogix client. This removes the first real
  runtime blocker on the connect/discover path.
- Fixed discovery tree building for pylogix atomic types that were recognized
  by discovery but missing from `TagDataType` (`USINT`, `UINT`, `UDINT`,
  `ULINT`, `TIME`, `LTIME`, `DATE`, `TIME_OF_DAY`, `DATE_AND_TIME`).
- Made program-scope tag enumeration best-effort. A controller that allows
  controller-scope tag discovery but rejects `GetProgramsList()` or one
  `GetProgramTagList()` call should still open with the tags already found.
- Blank pylogix status strings now produce an actionable discovery error
  instead of an empty `Could not discover tags:` dialog.
- Wired the Export button on the Export tab: it was created but never
  connected. The button now runs export for the selected sources/formats and
  reports results (or per-format errors, e.g. Excel without openpyxl) in the
  status label instead of a blocking dialog.
- Per-PLC watch list isolation: the Monitor tab watch list now clears when
  disconnecting, so tags from PLC A never bleed into PLC B's monitor with
  "Quality: Bad" values.
- Single-tag removal from the Monitor tab: each row now has a small `X` remove
  button so operators can drop one tag without clearing the entire list.
- Fixed unreadable QMessageBox/Read-history dialog: added explicit dark-themed
  styling for QMessageBox, QDialog, and their child labels so popups render with
  dark background and light text instead of the OS system palette.
- Inspector panel redesigned as a card-based layout: hero value, wider
  sparkline, and an inline recent-reads table (last 10 samples with timestamp,
  value, quality). No more huge blank space with 3 lines of text.
- Browse tree now has a "Value" column: populated on-demand when the operator
  clicks a leaf tag and the inspector reads it. No separate polling thread.
- Added dead-control audit harness (`tests/test_dead_controls.py`) that
  mechanically clicks every QPushButton in the app and verifies a side effect.
  This catches the bug class (buttons created but never connected) before the
  user sees it. Behavioral tests cover all 10+ app buttons.
- Replaced `QObject.receivers()`-based structural audit (unreliable with
  PySide6 Python signal connections) with behavioral click-and-verify tests.
- Wired the Browse inspector action buttons (Copy tag path, + Add to Monitor,
  Read history). They were created but never connected, so all three did
  nothing when clicked. Copy now writes the full tag path to the clipboard,
  Add to Monitor adds the tag to the watch list and brings the Monitor tab
  forward, and Read history shows the rolling per-tag read log.
- Inspector no longer auto-reads UDT/struct parent nodes. Issuing an aggregate
  read on a UDT root (e.g. `PIT204`) is rejected by Logix with a privilege
  violation; the inspector now reads only atomic leaf members and prompts the
  operator to select a member (e.g. `PIT204.PV`). Write tags are disabled for
  Add to Monitor (read-only in v2.0).
- Fixed unreadable text on the Export tab: `QCheckBox`/`QRadioButton` had no
  color rule in the stylesheet and fell back to near-black text on the dark
  background. Added explicit light-on-dark styling for checkboxes, radios,
  tooltips, and combo-box popups.
- Fixed `AttributeError("module 'plck' has no attribute 'discovery'")` on
  discovery: `plck/__init__.py` advertised `plck.discovery.discover_tags` as
  public API but never imported the submodule, so the worker's
  `plck.discovery.discover_tags(...)` reference failed. The package now imports
  its submodules (`comms`, `discovery`, `export`, `db`).
- Made `openpyxl` an Excel-only lazy dependency. The earlier submodule import
  pulled `openpyxl` at startup, so a `.venv` without it crashed launch with
  `ModuleNotFoundError: No module named 'openpyxl'`. Launch, discovery,
  monitoring, and JSON/XML export no longer import `openpyxl`; Excel export
  raises an actionable `RuntimeError` if the package is absent.

#### Added
- `Run_PLC_Toolkit_v2.bat` — checkout launcher for the PySide6/pylogix v2 GUI.
- `ab_poller/requirements-v2.txt` — pinned runtime/test dependencies for the
  v2 GUI path.
- `ab_poller/tests/test_app_startup.py` — startup regression tests for scratch
  DB/export overrides and the module entrypoint.
- `ab_poller/tests/test_worker_threading_contract.py` — regression tests to
  prevent UI-thread `PLCClient` instances from being passed into worker threads.
- `ab_poller/tests/test_discovery_types.py` — regression tests for pylogix
  atomic data types and array notation.
- `ab_poller/tests/test_discovery_programs.py` — regression test that program
  tag enumeration failures do not discard controller-scope discovery results.
- `ab_poller/tests/test_comms_errors.py` — regression test for non-empty
  pylogix status error messages.
- `ab_poller/tests/test_package_api.py` — regression test that
  `plck.discovery.discover_tags` resolves as a package attribute.
- `ab_poller/tests/test_export_optional_dep.py` — regression tests that
  importing `plck` never requires `openpyxl` and Excel export degrades to an
  actionable error when it is missing.
- `ab_poller/tests/test_browse_inspector.py` — regression tests that the
  inspector action buttons are wired, UDT roots are not auto-read and cannot be
  monitored, and write tags cannot be added to the monitor.

### Wireframes (`mockups/`)

The wireframes are static HTML/CSS for design review only — no code paths
back them yet. They are not the running product.

#### Added
- `mockups/index.html` — landing page that links to all 11 wireframe pages.
- `mockups/01-connection-manager.html` — saved-connections list, the
  first screen on launch.
- `mockups/02-new-connection.html` — connect-to-a-new-PLC dialog with
  connection-test panel.
- `mockups/03-discover-plcs.html` — subnet discovery dialog (modal). See
  the v2.0 scope decisions below.
- `mockups/04-workspace-browse.html` — Browse tab, tag tree with
  `+ Add to Monitor` action and live filter.
- `mockups/05-workspace-monitor.html` — Monitor tab, multi-tag real-time
  table, empty-state hint, polling interval selector.
- `mockups/06-workspace-export.html` — Export tab, three formats
  (Excel / JSON / XML), filename template, source radio.
- `mockups/07-workspace-history.html` — History tab, scan archive browser
  with NEW badge.
- `mockups/08-workspace-diagnostics.html` — Diagnostics tab, connection
  log and health checks.
- `mockups/09-settings.html` — settings dialog, six sections
  (Connection, Polling & Display, Discovery, Storage, Export, Advanced).
- `mockups/10-help.html` — keyboard shortcuts, glossary, About.
- `mockups/wireframe.css` — single shared stylesheet (industrial SCADA
  look, dark default, CLR blue + navy theme).
- `mockups/assets/` — CLR logo files.

#### v2.0 Scope decisions (locked in)
- **Single comms library: `pylogix`.** No dual-vendoring. The v1 binary's
  `pycomm3` is not carried forward. The upstream `pylogix` field gaps will
  be addressed with small upstream contributions or local helpers, not a
  second library. (Confirmed June 2026.)
- **Discovery protocol: EtherNet/IP only.** UDP 44818 (ListIdentity) +
  TCP 44818 (connection). v2.0. Modbus TCP and OPC UA Discovery are
  shown as disabled placeholders. Legacy DF1/CSPv4/SLC 5/05 are out of
  scope and not shown in the dialog.
- **Default poll rate: 5 s minimum.** Sub-5s polling against a
  CompactLogix / ControlLogix is restricted by the controller.
- **Symbolic addressing: always on.** No user setting; pylogix default.
- **BOOL display default: `0 / 1`** (matches Studio 5000 tag display).
  `FALSE / TRUE` and `Off / On` preserved as alternatives.
- **Storage path: `%APPDATA%\PLCToolkit\plc_data.db`.**
- **Scan archive path: `%APPDATA%\PLCToolkit\plc_scans\`.** Retention 90
  days by default, auto-prune on by default.
- **Theme default: Dark.** Light mode is opt-in and persisted in
  `localStorage.plc-theme`.

#### Discover dialog cleanups (2026-06-16, latest)
- **Scope modes use one address format: `IP / CIDR`.** Auto mode now
  shows `Ethernet — 10.20.30.0 /24` instead of
  `Ethernet — 10.20.30.100 / 255.255.255.0`. The three modes (Auto,
  Specific IP, Custom subnet) all use the same `IP / CIDR` form.
- **Removed "Show advanced" toggle from Custom subnet row.** The CIDR
  input is visible immediately when the radio is selected. Selecting
  the radio is itself the opt-in.
- **Probe list reworked.** Header reads `Allen-Bradley (Ethernet/IP)`,
  subtext reads `UDP 44818 / TCP 44818`. The defensive
  "Only EtherNet/IP is supported in v2.0..." note was removed at user
  request.
- **Status hint updated** to match the new address format.

#### Theme controller
- All 11 pages have a `<div class="theme-toggle">` in the topbar with
  Light / Dark buttons and a shared IIFE controller that reads/writes
  `localStorage.plc-theme`.
- All 11 pages now hardcode `<body class="theme-dark">` to prevent
  flash-of-light-content on first paint (the IIFE still swaps the class
  correctly for users who pick Light).

### Critical-eye wireframe review (2026-06-16)

Two independent reviews of the 11 wireframe pages + `wireframe.css`:
1. **Operator review** — first-time SCADA operator, basic Windows
   literacy, no v1 experience.
2. **UX/UI expert review** — accessibility, IA, error states, theme,
   cross-page consistency, destructive-action safety.

Both reviews were read-only. **No wireframe files were modified as part
of the review.** A leftover review note file at
`mockups/_REVIEW_NOTE.md` was deleted.

**Combined severity counts:**
- BLOCKER: 6
- CONFUSING: 38
- MINOR: 22
- PRAISE: 7

**Top 5 issues both reviewers raised (ranked):**
1. `[BLOCKER]` Destructive actions have no confirmation dialog.
   Found on 6 surfaces: `Remove selected` (01), `Disconnect` (04–08),
   `Clear history` (05), `Delete` history row (07), `Clear log` (08),
   `Reset to defaults` (09). None are styled as destructive.
2. `[BLOCKER]` `pycomm3.LogixDriver` and `pycomm3 1.2.10` appear in
   the v2.0 wireframes at `04-workspace-browse.html:187` and
   `08-workspace-diagnostics.html:55-56`. Violates AGENTS.md hard
   rules #2 and #3 (v2 is pylogix-only). Fix in a follow-up commit.
3. `[BLOCKER]` Help page (10) is a stub. The `? Help` button in
   every topbar navigates to a page that says "not yet implemented."
   SCADA tool, operators will hit Help. Ship a minimum-viable help
   page or remove the `? Help` button until the page is real.
4. `[BLOCKER]` Modals (02, 03, 09) have no focus trap, no initial
   focus, no Escape-to-close. Operators using keyboards will tab out
   of the modal into the dimmed background.
5. `[BLOCKER]` Discover scan progress is opaque. The status hint
   reads `0 / 254 probed` for the entire scan with no live counter,
   no elapsed time, no estimated time remaining. A 30-second scan
   looks like a hang. The existing `■ Stop` button should be renamed
   `■ Cancel scan`.

**Other notable findings (CONFUSING tier, summary):**
- 23 unresolved DRAFT notes in the wireframes. Many have a "decision
  already made" answer in the note itself; just delete the DRAFT
  prefix and commit to the design.
- Status bar copy is hard-coded to `Connected 4m 32s | 14 reads/sec
  | 0 errors` on all 5 workspace tabs. Export tab should not show
  reads/sec; History tab should not show connection duration.
- The "X clicks from launch" badge in every topbar means nothing to
  operators. Remove.
- The "Tags: 142" count on Browse is right but the tree only shows
  24 leaves. Operators will look for the missing 118 rows.
- UDT bulk-add behavior: clicking `[+]` on a UDT row silently adds
  all leaf members. No confirm. Surprise behavior.
- `+ Add selected to my connections` on Discover is enabled at
  0 selections and has no bulk-add confirmation. Another footgun.
- `+ Add from Browse` on Monitor is a button that does nothing.
  Either open a tag-picker modal or rename it.
- Watch list `Last update` column shows `00:00:01` for all rows
  (placeholder). The format is misleading.
- `Writes / sec: 0` on Diagnostics implies writes are a feature.
  v2.0 is read-only — add a hint or remove the row.
- "READ-ONLY — no writes to PLC" should be a visible banner on
  workspace tabs, not just a rule in AGENTS.md.

**What the review explicitly praised:**
- Theme toggle is in every topbar.
- The `wireframe.css` design system is well-documented and
  honors the "gold is never clickable" rule.
- The `back-link` pattern on workspace tabs is correct (safe
  navigation; Disconnect is the destructive action).
- The `<body class="theme-dark">` hardcode + localStorage IIFE
  is the right desktop pattern (no flash of light content).
- The Discover dialog cleanup (Auto = IP/CIDR, drop "Show
  advanced", probe list rework, defensive note removed) shipped
  before the review and is consistent with the operator's
  expectations.

**Status:** Reviews completed and recorded. Wireframe edits gated
on per-action approval from the project owner.

### Tag inspector mockup (2026-06-16)

Built a "tag inspector" right-pane for `04-workspace-browse.html`
that fills the previously-empty right pane with a real, on-demand
single-tag read view. This is the alternative to merging Browse
and Monitor into one tab; the inspector keeps the two tabs separate
but makes Browse's right pane actually useful.

**What the inspector shows when a tree row is clicked:**
- Tag name + type chip (header).
- Quality dot (Good / Stale / Bad) + last-read timestamp.
- LARGE current value with engineering unit suffix.
- min / max / avg across the last 60 reads.
- 60-bar sparkline (theme-aware via `fill="currentColor"`).
- Three actions: `+ Add to Monitor` (primary), `Read history`
  (links to Diagnostics), `Copy tag path`.
- A note explaining the inspector vs. Monitor distinction.

**What the inspector does NOT do:**
- It does not add to the Monitor watch list automatically.
- It does not count against the Monitor poll cycle.
- It reads the selected tag every 2s on demand, only while that
  row is selected.

**Write-tag handling:**
- `StartCmd` / `StopCmd` rows are visually dimmed (55% opacity),
  italic, with an orange `cmd` pill.
- The `[+]` button on those rows is disabled (no hover, neutral
  border, `cursor: not-allowed`).
- Clicking a write tag still opens the inspector (read-only
  view of the current value), but the "Add to Monitor" button
  is disabled and labeled accordingly.

**UDT bulk-add affordance:**
- UDT parents now show leaf counts (`+8`, `+3`) instead of bare
  `+`, matching the `(N members)` annotation.

**State management:**
- Selected row gets `.is-selected` (blue accent left bar).
- Click anywhere on the row except the `[+]` action → swap inspector.
- Keyboard: Enter or Space on a focused row → swap inspector.
- JS controller swaps the inspector innerHTML on selection change
  with a deterministic per-tag sample value, so the reviewer can
  click through several tags and see the inspector populate.

**What this does NOT do (deferred):**
- No actual pylogix read yet — wireframe only.
- Inspector polling rate is fixed at 2s in the design; not yet
  user-configurable.
- Sparkline data is randomized per tag (deterministic) for visual
  variety; not yet backed by real read history.

### `ab_poller/` — cleanup completed (2026-06-16)

The dead code was actually inside `ab_poller/` (the source root), not at
the repo root. The repo root holds the *built* output (`PLC_Toolkit.exe`,
`plc_data.db`, `Run_Toolkit.bat`, `mockups/`). `ab_poller/` was the
source root: `plc_toolkit_consolidated.py`, the GitHub Actions workflow,
git history, and a long tail of superseded files.

#### Live build path (kept)
The live product is built from a single source file by `.github/workflows/build-windows.yml`
(and `build-simple.yml`):
`plc_toolkit_consolidated.py` (self-contained; imports stdlib +
`pycomm3.LogixDriver` + optional `openpyxl`) → `PLC_Toolkit.exe` via
PyInstaller → bundled into `dist_package/` with `Run_Toolkit.bat`.

#### Deleted (verified dead by import-graph analysis)
- `ab_poller/toolkit.py` — older version, superseded by
  `plc_toolkit_consolidated.py` ("Consolidated Version" header).
- `ab_poller/export_tool.py` — only imported by `toolkit.py` (dead).
- `ab_poller/tag_checker_tool.py` — only imported by `toolkit.py` (dead).
- `ab_poller/create_db.py` — nothing imports it. The live
  `plc_data.db` is self-created by `plc_toolkit_consolidated.py`
  via `CREATE TABLE IF NOT EXISTS` (lines 87 + 98).
- `ab_poller/schema.sql` — only referenced by `create_db.py` (dead).
  Describes `knowledge.db` which does not exist; live is
  `plc_data.db`. Stale and wrong.
- `ab_poller/update_memory.py` — only self-references itself.
- `ab_poller/windows_exe_helper.py` — print-only Mac→Windows build
  advisory. `build_windows.py` is the real builder.
- `ab_poller/make_exe.py` — superseded by `build_windows.py`.
- `ab_poller/make_exe_cross_platform.py` — `windows_exe_helper.py`
  pointed users here to set up the GitHub workflow; the workflow is
  already set up.
- `ab_poller/BUILD_WINDOWS_EXE.bat` — superseded by `BUILD_FOR_WINDOWS.bat`.
- `ab_poller/GITHUB_ACTIONS_FIX.md` — pre-fix writeup. The workflow
  was fixed in commit `cc7f69d` (Node 24-compatible Actions).
- `ab_poller/PACKAGING_GUIDE.md` — superseded by `README.md`'s
  "Windows executable" section + the GitHub Actions workflow.
- `ab_poller/PLC_Toolkit` (8.8 MB, no `.exe` extension) — stale
  Mac/Linux build output. The shipped binary is `PLC_Toolkit.exe`
  at the repo root, built fresh by GitHub Actions.
- `ab_poller/build/` — PyInstaller intermediate directory
  (`build/PLC_Toolkit/` + `build/PLC_Toolkit.spec`). GitHub Actions
  runs PyInstaller in CI; this was a local leftover.

#### Kept (load-bearing)
- `ab_poller/plc_toolkit_consolidated.py` — live source.
- `ab_poller/build_windows.py`, `BUILD_FOR_WINDOWS.bat` — live build path.
- `ab_poller/.github/workflows/build-windows.yml`,
  `ab_poller/.github/workflows/build-simple.yml` — live CI.
- `ab_poller/pylogix_migration_analysis.md` — v2.0 design analysis.
- `ab_poller/README.md` — project README.
- `ab_poller/.gitignore`, `ab_poller/.git/`, `ab_poller/.venv/`,
  `ab_poller/.claude/` — dotfiles / venv / git metadata.

### Removed (was wrongly present)
- Settings: Read batch size (not a real pylogix option).
- Settings: Display REAL as decimal (not a real pylogix option).
- Settings: Telemetry (no product need, conflicts with no-telemetry rule).
- Settings: Proxy (pylogix does not support HTTP/SOCKS proxies for raw
  TCP PLC traffic).
- Settings: legacy probe checkboxes (CSPv4, SLC EtherNet).
- Discover dialog: "Only EtherNet/IP is supported in v2.0..." defensive
  note.
- Discover dialog: "Show advanced" toggle on the Custom subnet row.

---

## [1.0.0] — 2025-09-02 — Initial v1 binary release
- First build of the live TUI executable. `plc_toolkit_consolidated.py`
  compiled via PyInstaller to `PLC_Toolkit.exe`. `pycomm3.LogixDriver`
  for EtherNet/IP. Excel / JSON / XML export. `plc_data.db` with `plcs`
  and `tag_data` tables. Built by GitHub Actions on 09/02/2025 16:46:14.
