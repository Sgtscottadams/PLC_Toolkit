# PLC Toolkit — Project rules for AI coding tools

This file is read by AI coding assistants (Cursor, Claude Code, OpenCode,
Hermes) when they open this project. **If you are an AI: read this file
in full before making any change.**

The human author of the project is Scott, SCADA Supervisor at Continental
Resources. He is the original author of the v1 TUI and is leading the
v2.0 GUI rebuild.

---

## Surfaces and scope

> **Naming note (2026-06-29):** version suffixes were stripped from file
> names. The GUI is now the product and builds to `PLC_Toolkit.exe` at the
> repo root. The original pycomm3 TUI was moved to `legacy/`. The version
> still appears in **Help → About** and in `CHANGELOG.md`; it is no longer
> baked into file names. References to "v1"/"v2" below describe the two
> code surfaces and their comms-library rules, which still apply.

1. **The GUI (`ab_poller/plc_toolkit/`, `ab_poller/plck/`)** — the live
   product. `pylogix`-based (EtherNet/IP), PySide6 UI. Builds to
   `PLC_Toolkit.exe` at the repo root via `ab_poller/build_windows.py`.
   The source root is `ab_poller/`.
2. **Legacy TUI (`legacy/`)** — the original `pycomm3`-based consolidated
   binary (`legacy/PLC_Toolkit.exe`) and its source
   (`ab_poller/plc_toolkit_consolidated.py`, kept in place so its tests
   resolve). Archived/frozen; do not add features. Reference only.
3. **`mockups/`** — static HTML/CSS wireframes for design review. **No
   code paths back the wireframes yet.** Editing a wireframe changes the
   design, not the product.

When asked to "review the work," default to: read the GUI runtime surface
first, then the wireframes, then the dead-code audit.

---

## Hard rules

These are non-negotiable. If a task appears to require breaking one,
stop and ask before acting.

1. **The v1 live binary is the source of truth for what v1 does.** If
   the wireframe disagrees with the v1 binary, the binary wins until v2
   ships. Do not "fix" the wireframe to match a v2.0 redesign that
   hasn't been implemented yet.
2. **No new `pylogix` features go into the v1 binary.** v1 is
   `pycomm3`-based. v2 is `pylogix`-based. Don't merge them.
3. **One comms library per release.** v2 is `pylogix`-only. If a field
   is missing in `pylogix`, prefer a small upstream contribution or
   local helper over vendoring a second library. This was confirmed in
   June 2026 and is not open for re-debate.
4. **No telemetry, no analytics, no third-party identifier tagging.**
   SCADA networks are isolated. No opt-in was given.
5. **Per-action explicit approval for any change to data, configs, or
   live systems.** Read-only review is the default. If a task says
   "review" or "check" or "audit," do not write files.
6. **Every code or wireframe change is recorded in `CHANGELOG.md`.**
   Add a dated entry under the appropriate section. The entry should
   name the file(s) and the behavior change, not just "fixed bug."
7. **Every change to this file (`AGENTS.md`) is recorded in
   `CHANGELOG.md`** under the "v2.0 GUI rebuild" section, not silently.

## Soft conventions

- **The user is the project owner and the domain expert.** Don't
  explain SCADA, PLCs, EtherNet/IP, CompactLogix, ControlLogix, or
  `pylogix` basics back to him. He wrote the v1 binary.
- **One question per turn during design discussion.** He has said this
  verbatim: "parallel threads for design are fine once the plan is
  approved, but no shotgun of questions."
- **Multi-agent / parallel subagent execution is preferred** during
  research, wireframe generation, and read-only review. Confirm
  subagent results on disk before claiming them done.
- **No fabricated output.** If a subagent claims success, verify the
  claim on disk. If a tool, install, or network call fails, say so
  directly. Never substitute plausible-looking fabricated output for
  results that could not be produced.
- **No silent guessing.** Flag unknowns explicitly. "I don't know" is
  acceptable; a confident wrong answer is not.

## Wireframe conventions

- The 11 wireframe pages are siblings. Anything that changes theme
  behavior, navigation, or the global layout must be applied to all
  11 pages, not just the page you are editing.
- The `<div class="theme-toggle">` block + the IIFE controller that
  reads/writes `localStorage.plc-theme` are shared. To copy them
  between pages, copy the entire topbar block and the entire
  `<script>` block at the bottom of the page.
- All 11 pages hardcode `<body class="theme-dark">` to prevent
  flash-of-light-content. Don't remove that without coordinating.
- The `back-link` on workspace tabs (04, 05, 06, 07, 08) goes to
  `01-connection-manager.html`. It keeps the PLC connection alive.
  Don't link it elsewhere.

## v2.0 scope (locked)

GUI rebuild, Scope A. Wrap the three v1 TUI features in a windowed GUI:
connect/discover, read-monitor, export. Add: tag search/filter,
multi-tag simultaneous monitor, real-time charts, scan history
persistence.

**Deferred** (do not implement without explicit approval): multi-PLC
concurrent polling, saved connection profiles, history diffing,
write-back to the PLC.

## Forbidden additions in v2.0 (don't re-add these)

These were removed in the wireframes on 2026-06-16. Re-introducing any
of them is a regression unless the user asks for it.

- "Show advanced" toggle on the Custom subnet row in the Discover
  dialog. The CIDR input is the advanced bit; the radio is the opt-in.
- A defensive "Only EtherNet/IP is supported in v2.0..." note on the
  probe list. The scope is what it is; the dialog shows what is in
  scope.
- The `pycomm3` library, the `pycomm3.LogixDriver` symbol, or any
  reference to a second comms library alongside `pylogix`.
- The legacy probe checkboxes (CSPv4, SLC EtherNet) and the explanatory
  DRAFT about why they were removed.
- A "Read batch size" setting (pylogix does not expose one).
- A "Display REAL as decimal" setting (pylogix does not expose one).
- A "Telemetry" / "Proxy" / "Verify TLS" setting in v1.0. (TLS does
  not apply to raw CIP traffic; telemetry is off by rule; pylogix does
  not support HTTP/SOCKS proxies.)

## How to use this file

- An AI opening the project: read this file first, then `CHANGELOG.md`,
  then the file you are about to change.
- A reviewer: if a PR or change-set violates a hard rule, the change
  is rejected, period. Soft conventions are nudges, not blockers.
- A contributor adding a hard rule: also add a `CHANGELOG.md` entry
  naming the rule you added.
