# PLC Toolkit

Allen-Bradley EtherNet/IP tag discovery, live monitoring, and export.

## Surfaces

| Surface | Launch | Comms | Status |
|---------|--------|-------|--------|
| **PLC Toolkit (GUI)** | `Run_Toolkit.bat` (portable) or `Run_PLC_Toolkit.bat` (dev) | pylogix + PySide6 | **Active — MVP field test** |
| Legacy TUI | `legacy/Run_Toolkit.bat` → `legacy/PLC_Toolkit.exe` | pycomm3 | **Archived** — superseded by the GUI |

The current product is the PySide6 GUI. The original pycomm3 TUI has been
retired to `legacy/` and is kept for reference only. Version history lives in
`CHANGELOG.md`; the running build reports its version in **Help → About**.

Source root: `ab_poller/`

## Run from source (developers)

```powershell
cd ab_poller
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m plc_toolkit
```

Or from repo root: `Run_PLC_Toolkit.bat`

## Build portable package (field deploy)

```powershell
cd ab_poller
.\BUILD_PORTABLE.bat
```

Or: `.\.venv\Scripts\python.exe build_windows.py`

**Send users:** `dist_package/PLC_Toolkit_Windows.zip`

Extract the entire zip on the target PC or server share. **Double-click
`PLC_Toolkit.exe`** inside the extracted folder. No Python install required.

Optional shortcuts (same program) live in `extras/`: `Launch PLC Toolkit.vbs`
(no command window) and `Run_Toolkit.bat`.

The extracted root is intentionally clean — only the exe plus folders:

```
PLC_Toolkit/
  PLC_Toolkit.exe             ← double-click this
  assets/                     Continental logo
  data/                       settings.json, portable.marker, plc_data.db
  scans/                      saved scan archives
  exports/                    Excel / JSON / XML exports
  extras/                     optional launchers + Quick_Start / MVP_PILOT
```

`Run_PLC_Toolkit.bat` at repo root is **dev/source only**.

## Tests

```powershell
cd ab_poller
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

## MVP pilot checklist

Before signing off MVP with operators:

1. Extract zip to test folder; double-click **`PLC_Toolkit.exe`** — loading splash then main window
2. Settings → Storage shows paths under the extracted folder (`data\`, `scans\`, `exports\`), not `%APPDATA%`
3. Subnet scan finds known PLCs (or shows actionable empty-result message)
4. Connect from saved list — Browse tab shows discovery banner; window stays responsive
5. Browse tree loads on a representative field PLC without "Not Responding"
6. Monitor watch list, export (Excel/JSON/XML), History snapshot round-trip
7. Help (F1) opens troubleshooting and glossary

## Data paths

**Portable deploy** (default when using `Run_Toolkit.bat`):

- Database: `{app folder}\data\plc_data.db`
- Scan archives: `{app folder}\scans\`
- Exports: `{app folder}\exports\`

**Dev/source** (no portable flag): `%APPDATA%\PLCToolkit\`

Override for tests: `PLC_TOOLKIT_DB`, `PLC_TOOLKIT_OUTDIR`

## Scope

The MVP is **read-only** — connect, discover, monitor, export. No write-back to the PLC.

See `AGENTS.md` and `CHANGELOG.md` at repo root for locked scope and change history.
