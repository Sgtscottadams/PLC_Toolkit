# PLC Toolkit — Project Status

> **Read first** every session.
>
> **Owner:** Scott Adams · **Last updated:** 2026-06-26

---

## Summary

Desktop tool for **Allen-Bradley PLC** connectivity: browse tags, monitor values, export data. The product is the PySide6 + pylogix **GUI** under `ab_poller/`, built to `PLC_Toolkit.exe` at the repo root. The original pycomm3 TUI is archived in `legacy/`. Version is shown in **Help → About** and tracked in `CHANGELOG.md`; file names are no longer version-suffixed.

---

## Current focus

| Priority | Work item |
|----------|-----------|
| **Now** | GUI in `ab_poller/plc_toolkit/` — see `ab_poller/README.md` |
| **Next** | Portable build via `BUILD_PORTABLE.bat`; pilot field test |
| **Guardrail** | GUI is read-only (no write-back); legacy TUI kept in `legacy/` for reference |

---

## Done

- GUI built to `PLC_Toolkit.exe` at repo root
- Test suite (150+ tests under `ab_poller/tests/`)
- Portable packaging in `dist_package/`
- Legacy pycomm3 TUI archived in `legacy/`
- `AGENTS.md` with scope rules

---

## In progress

- GUI MVP field validation against representative PLCs
- Wireframes in `mockups/` (design only — not runtime)

---

## Known issues

| Issue | Notes |
|-------|-------|
| Legacy TUI | Archived in `legacy/`; do not conflate its behavior with the GUI |
| No git repo yet | Consider init now that the rename has stabilized the layout |

---

## How to run

```powershell
# Dev (run from source)
.\Run_PLC_Toolkit.bat

# Tests
cd ab_poller
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

---

## Documentation map

| File | Purpose |
|------|---------|
| **`PROJECT_STATUS.md`** | This file |
| `AGENTS.md` | AI rules (scope, comms library) |
| `ab_poller/README.md` | technical readme |
| `CHANGELOG.md` | Release notes |

---

## Git

**Not initialized.** Local folder only.

---

## For AI agents

- Read **`AGENTS.md`** before any code change (comms-library separation still applies; legacy TUI in `legacy/` is frozen).
- Update this file when release scope or blockers change.
