# PLC Toolkit v2.0 Wireframe Review — Operator's Eyes

**Reviewer:** First-time SCADA operator. Basic Windows literacy. Knows what a PLC is, knows what an IP address is, knows EtherNet/IP exists. Not a programmer. Has never used PLC Toolkit v1.
**Scope:** All 10 functional wireframes (01–10) + `wireframe.css`.
**Mode:** Read-only. No edits made. The intent of this review is to surface what an operator actually experiences walking through the app cold, not to redesign.

---

## Global observations (apply to multiple pages)

**G1. PRAISE — Theme toggle lives in the top bar of every page.** Consistent, predictable, doesn't require digging into Settings to find. Good call.

**G2. CONFUSING — Draft notes are leaking into the operator UI.** Every page except the help screen has visible `[DRAFT: question for user]` notes (e.g. page 04 has three of them stacked above the right pane). As an operator, I do not know what these mean. They look like error messages or developer scaffolding that escaped. Strip them before any user sees the app, or hide them behind a "Show design notes" toggle that defaults off.

**G3. CONFUSING — "X clicks from launch" badge in the top right of every page.** As an operator I have no idea why I need to know the click distance from the start screen, and the metric itself is a developer artifact. Remove from the shipping UI.

**G4. CONFUSING — The breadcrumb at the top of every page is fine, but the workspace pages (04–08) all use a slightly different topbar layout (back-link + title + actions) than the modal pages (02/03/09) which use a different pattern (no back-link, just dimmed chrome).** As an operator, I can't tell whether "← Connections" on the workspace pages is the same as "✕" on a modal or whether one is destructive and the other is not. The CSS comment says "back-link is the safe navigation; Disconnect is the destructive action" — that distinction is invisible to me.

**G5. BLOCKER — The Diagnostics page (08) and the status bar on the Browse page (04) both display `Driver: pycomm3.LogixDriver` and `Driver version: pycomm3 1.2.10`.** This contradicts the project rule "v2 is pylogix-only" (AGENTS.md hard rule #3, forbidden-additions list explicitly bans `pycomm3.LogixDriver`). As an operator I wouldn't catch the library name, but a support tech reading the diagnostic dump would be misled into thinking v2 is the wrong build. The v2.0 driver line should read `pylogix.PLC` and `pylogix <version>`, consistent with the comment in `02-new-connection.html` line 158.

---

## 01-connection-manager.html

**01-1. PRAISE — "Saved connections" is the first thing I see.** Clear primary surface. Good.

**01-2. PRAISE — The big blue `+ Connect to a new PLC` button is unmissable.** Primary action is obvious. The secondary `Discover on subnet` sits next to it as a clear alternative. Good hierarchy.

**01-3. CONFUSING — I have no idea what "last seen 0h ago / 2h ago / 1d ago / 5d ago" actually means.** Does "last seen" mean the last time I successfully connected to this PLC? The last time it responded to a ping? The last time the entry was edited? As an operator I'd want to know: "is the PLC currently reachable, or am I looking at a stale entry?" Add a column for "Reachability" or a small status dot (green/amber/red) next to the nickname — that would tell me at a glance which rows are safe to click `Connect` on and which I should expect to fail.

**01-4. CONFUSING — The "5d ago" row (LACT Unit 3) looks identical to the live ones.** No visual difference. If it's stale, that should be apparent before I click. (Same fix as above.)

**01-5. CONFUSING — "Slot 0" and "Slot 2" columns with no explanation.** I know what a slot is from ControlLogix work, but a less experienced operator may not. A tiny hint or tooltip ("processor slot number, 0 for most ControlLogix") would help. Also: do I ever need to change the slot from this screen? If not, why is it shown?

**01-6. CONFUSING — The checkboxes on each row enable a "Remove selected" / "Rename selected" toolbar, but that toolbar is muted and easy to miss.** As a first-time operator I wouldn't notice the "0 selected" affordance. If the row checkboxes are the entry to bulk actions, they should be more discoverable, or the row-level `Connect` button should be the obvious path (which it currently is — so the checkboxes are basically dead weight for a first-time user).

**01-7. BLOCKER — "Remove selected" has no confirmation step.** A misclick deletes a saved connection. As an operator who manages dozens of PLCs, I'd want a "Are you sure you want to remove N connections?" prompt, or at least an undo (Cmd+Z / Undo button). Right now, one accidental click and an entry is gone, and I have to re-enter the IP and slot from memory.

**01-8. CONFUSING — Empty state for first-time use is collapsed as an HTML comment.** The wireframe shows a draft note asking what the empty state copy should be, then has the recommended empty state in a `<!-- ... -->` block. I never see it. For an operator who just installed the app, this is the first impression. Ship the empty state with the agreed copy (the proposed wording in the comment is fine: "No saved connections yet. Click `+ Connect to a new PLC` or `Discover on subnet` to get started.").

**01-9. MINOR — Status bar says `Status: Not connected.` and `Ready.`** "Ready" is a no-op. Either say something useful ("No connections yet — click `+ Connect to a new PLC`") or drop it.

---

## 02-new-connection.html

**02-1. PRAISE — "Nickname" as the first field is the right call.** Operators name PLCs. Starting with IP would be backwards.

**02-2. PRAISE — "Processor Slot" defaults to 0 with a hint "Most ControlLogix/CompactLogix are slot 0."** This is exactly the right level of hand-holding.

**02-3. CONFUSING — "CIP Path" sits behind "Show advanced" with a hint "Backplane path; leave blank for default (slot only)."** As an operator, "CIP Path" is jargon. I don't know what "backplane path" means versus "slot only." The hint is too brief. The fact that this is collapsed into "advanced" is good (most operators won't need it), but the label needs either a one-line explainer or a tooltip.

**02-4. CONFUSING — "Port" defaults to 44818 with no hint at all.** I know 44818 is EtherNet/IP from my own reading, but a coworker who hasn't been around EtherNet/IP as long wouldn't. One-line hint ("EtherNet/IP port — 44818 is the default") would prevent a tech from changing it to something arbitrary and then wondering why nothing connects.

**02-5. CONFUSING — "Timeout (s)" defaults to 5 with no hint.** What does this number affect? "How long to wait for a response before giving up" is what I'd guess, but I'm not sure. Add a hint.

**02-6. PRAISE — The `Test connection` button sits in the modal footer with `Cancel` and `Connect` as siblings.** Three-button pattern is correct (test, cancel, primary). Good.

**02-7. CONFUSING — "Test connection" workflow is invisible in the static wireframe.** The test result panel is `<div ... id="nc-test-result" hidden>` until I click. As an operator, I don't know that clicking `Test connection` will *show* me a result, or what the result will look like. Add a one-line hint next to the button: "Verifies the IP responds and the slot is correct." Or have the result panel always visible (in its "idle" state) so the operator knows there's a slot for feedback.

**02-8. CONFUSING — `Save to my connections` is checked by default.** That's fine for repeat connections, but for a brand-new user trying out the app with a test PLC, the default could be wrong. Either:
   - Default to unchecked if "Nickname" is empty (force an explicit "yes, save this" decision), or
   - Default to checked but add a hint explaining that "Save to my connections" means it appears on page 01.

**02-9. MINOR — `✕` close button in the top-right of the modal is the only way to dismiss without clicking `Cancel` or `Connect`.** That's actually correct. Pressing Esc should also close — the wireframe doesn't show a keyboard handler, but that's expected for static HTML. Note for the implementation.

**02-10. CONFUSING — "Show advanced" has a draft note asking whether Port and Timeout should be in the advanced section or at top level.** As an operator: **keep them in advanced.** The only field 90% of operators will touch is Nickname, IP, and Slot. Showing Port and Timeout at the top invites people to mess with values they don't understand. If they're in advanced, only people who know what they're doing will find them. The current placement is right.

---

## 03-discover-plcs.html

**03-1. CONFUSING — The three "Scope" modes are listed as Auto, Specific IP, and Custom subnet — but as a first-time operator, the words don't tell me what they do.** I have to read the long draft note below them to figure out:
   - **Auto** = broadcast to every interface
   - **Specific IP** = probe one PLC I already know about
   - **Custom subnet** = sweep a range I type in

   The labels are accurate but bare. A short one-line description under each radio would close the gap. The CSS already has a `.hint` styling; use it.

**03-2. CONFUSING — The Auto mode dropdown shows three interfaces: `Ethernet — 10.20.30.0 /24`, `Wi-Fi — 192.168.1.0 /24`, `Ethernet 2 — 172.16.0.0 /16`.** That implies I should pick which interface to scan, but the draft note underneath says "in v2.0 the discovery still broadcasts to 255.255.255.255 on every interface." So the dropdown is decorative — choosing `Wi-Fi` doesn't actually do anything. That's a UX bug: the dropdown invites a choice that has no effect. Either (a) the dropdown should drive actual per-interface behavior, or (b) it should be removed and replaced with "Auto scans all your network interfaces."

**03-3. CONFUSING — Status line says `Scope: Auto on Ethernet — 10.20.30.0 /24. 0 / 254 probed.`** This updates live as I change inputs. Good. But the numbers are slightly misleading: in Auto mode, broadcasting to 255.255.255.255 does NOT probe 254 hosts on one interface — it probes whatever responds on every interface. The "0/254" framing is a /24-network assumption that's wrong for Auto. Either fix the math, or simplify the status line to "Idle. Click Start scan."

**03-4. CONFUSING — Probe list shows three protocols, but two are grayed out as "future, disabled."** That's fine for a roadmap signal, but the wireframe also has a draft note saying the v2.0 design philosophy is "the scope is what it is; the dialog shows what is in scope." If that's the philosophy, the disabled Modbus TCP and OPC UA checkboxes shouldn't be visible at all — they're clutter that implies they're coming soon. Remove the grayed-out rows; ship the dialog showing only EtherNet/IP.

**03-5. CONFUSING — "Start scan" vs "Stop" buttons in the same row.** A first-time operator might not know that once a scan starts, the button text changes (or that they can cancel). Either disable "Stop" until "Start scan" is clicked, or add a tiny hint "Click to begin. The button switches to Stop during the scan."

**03-6. BLOCKER — `+ Add selected to my connections (0 selected)` button is always enabled.** As an operator with a subnet of 50 PLCs, I could check 50 rows, click this, and end up with 50 new saved connections with auto-generated nicknames (or worse, blank nicknames if the field is empty). The button should be disabled when 0 are selected, AND there should be a confirmation step showing what I'm about to add: "Add 3 PLCs to your saved connections: 10.20.30.41, 10.20.30.42, 10.20.30.50 — Continue?" This is a bulk-write action.

**03-7. PRAISE — The Results table has an empty state (`No results yet. Click Start scan.`).** Good. Don't ship without it.

**03-8. CONFUSING — The DRAFT note for "Scope behavior" is enormous and pushed to the top of the modal.** It explains developer intent. As an operator, I'd never read it. It should be a tooltip on a `(?)` next to "Scope," not a 6-line block.

**03-9. CONFUSING — The "Custom subnet" radio is labeled `Custom subnet (advanced)`.** The "(advanced)" tag is good, but the radio itself doesn't visibly differ from the other two. A first-time operator may not realize the warning. Consider dimming the row by default and making it visibly opt-in.

---

## 04-workspace-browse.html

**04-1. CONFUSING — On the first launch of the workspace, I land on `Browse*` with the asterisk.** The asterisk isn't explained anywhere on the page. Looking at the CSS, I see the asterisk marks the current tab. As an operator, the asterisk is invisible (small, in a non-obvious position) and doesn't add information — the active tab is already bold and underlined. Either remove the asterisks (they're redundant) or document what they mean.

**04-2. CONFUSING — The right pane is just an empty placeholder: `Browse tags on the left to read their values, or switch to another tab.`** This is the operator's main view once connected, and it offers *nothing* of value out of the box. There's no value preview, no last-update timestamp, no quality indicator. As an operator I clicked `Connect` to *see what's on the PLC*, and this screen says "go find a tag in the tree, click on it, and we'll show you something." Even a tiny "Current connection: 4m 32s, 142 tags discovered" header in the right pane would be more reassuring. The wireframe has a draft note asking whether to show last-update + 60s trend there. **Yes, do it.** Without it, the right pane is dead space.

**04-3. PRAISE — The tree-hint at the top of the left pane (`Click [+] on a row to add it to the Monitor watch list, or right-click for more options.`) is the right kind of coaching.** As a first-time operator, this is what tells me the app has more than one affordance. Keep it.

**04-4. CONFUSING — The `[+]` button on a UDT parent row (e.g. `Pump_01`) is unlabeled beyond its `title="Add Pump_01 to monitor"`.** As an operator, I'd guess clicking `[+]` on a UDT adds *the UDT* to the monitor, not its members. The draft note on the right-click menu says "for a UDT row, all leaf members" — so clicking `[+]` on `Pump_01` adds 8 members. That's surprising behavior for a one-click button. Either:
   - Click `[+]` on a UDT row opens a small "Add Pump_01 to monitor? (8 leaf tags will be watched)" confirm dialog, or
   - The `[+]` on UDT rows is visually different (e.g. `[+]` vs `[+8]`) and the operator must confirm the bulk add, or
   - Disable `[+]` on UDT rows and require right-click → "Add to Monitor (members)" to be explicit.

**04-5. CONFUSING — `Pump_01.StartCmd` and `Pump_01.StopCmd` are BOOL tags in the same row list as `Pump_01.Status` and `Pump_01.Speed`.** All four have the same `[+]` affordance. As an operator, I'd happily click `[+]` on `Pump_01.StartCmd` to "monitor" it, not realizing I'm now able to *see* a write-tag (a command). The wireframe correctly excludes any "write" action, but the *display* doesn't distinguish read-only tags from command tags. Add a visual cue: a small "cmd" or "R/W" pill next to command tags, or grayed-out `[+]` for write tags. This is a **safety** concern, not just a usability one — a future version with write-back would be one click away from a footgun.

**04-6. CONFUSING — The right-click context menu is documented in a DRAFT note only.** As a first-time operator, I cannot tell whether right-click *actually does anything* in the running app. The note says "(proposed — confirm with user)" and lists 5 menu items. The note itself is good documentation, but as a user, I have no way to learn the menu exists. Either document it inline in the tree-hint (`Click [+] or right-click for: Add to Monitor, Read value now, Copy tag path, View in Diagnostics`) or include a small "?" icon that opens a popup with the menu items.

**04-7. PRAISE — Search bar at the top: `Search:` with placeholder `filter tags… (e.g. Pump_01, Level, Status)`.** Good. Concrete examples in the placeholder teach the operator what to type.

**04-8. CONFUSING — `142 tags discovered` count sits next to `Re-discover` button.** As an operator, "Re-discover" could mean "search the PLC again" (expensive) or "refresh the tag list" (cheap). Without a hint, I'm scared to click it on a real PLC because I don't know if it'll disrupt anything. Add a hint: "Re-scans the PLC and replaces the current tag list (~3s)."

**04-9. PRAISE — Status bar `Connected 4m 32s | 14 reads/sec | 0 errors`.** Excellent. The exact information an operator wants to see at a glance.

**04-10. BLOCKER — Status bar shows `Driver: pycomm3.LogixDriver`.** This is the v1 driver, not the v2 driver. See global finding G5. As an operator I wouldn't catch it, but a tech pasting this into a support ticket would be misled.

**04-11. CONFUSING — `↩ Connections` back-link in the top-left vs `Disconnect` button in the top-right.** The CSS comment explains the difference (back is safe nav, Disconnect is destructive), but as an operator, I have to read tooltips to figure that out. Tooltip on Disconnect should be very explicit: "Disconnects from this PLC. You'll go back to the Connection Manager but any unsaved Monitor changes will be lost." Or — better — make Disconnect ask for confirmation. Right now, one click kills the connection.

**04-12. CONFUSING — `Disconnect` in the top-right is styled as a plain `.btn`, not a destructive button.** A plain button with the word "Disconnect" reads as safe. Disconnect is the destructive action on this screen. Style it red or with a warning border, OR move it into a small "session" menu.

---

## 05-workspace-monitor.html

**05-1. CONFUSING — The hint at the top of the watch list says "Open the Browse tab, right-click a tag, 'Add to watch list'." But on page 04 (Browse), the right-click menu is documented in a DRAFT note, not in the actual UI.** As a first-time operator, the path `Browse → right-click → Add to watch list` is invisible. The first instruction in the hint should match the only visible affordance on Browse, which is the `[+]` button. **Suggestion: change the hint to "Open the Browse tab and click [+] on any tag, or use [+ Add from Browse] below."** (And the right-click path is a power-user shortcut; mention it second.)

**05-2. CONFUSING — `+ Add from Browse` button sits at the top of the watch list.** Does it open a tag picker (modal with the full tree)? Or does it just navigate to the Browse tab? As an operator, the button text doesn't tell me. Add a hint under the button: "Opens a tag picker so you can find and add tags without leaving this tab." (This is a *better* affordance than the [+] on each tree row because it works in batches.)

**05-3. PRAISE — The watch list table has `Tag | Type | Current value | Quality | Trend (last 60 samples) | Last update`.** As an operator, this is exactly what I want. The columns are self-explanatory.

**05-4. CONFUSING — The trend column is an SVG of gray rectangles.** I know from the CSS this is a placeholder for a real sparkline, but in a wireframe shown to an operator, this looks like a static graphic. If this is a wireframe for review purposes, fine. If an operator will see this on day 1, the SVG should be replaced with the text `(no data yet)` or `[trend placeholder]` until the real data starts flowing.

**05-5. CONFUSING — "Quality" column shows `Good` for all three rows, but I have no idea what the other values would be.** A `Good` / `Bad` / `Uncertain` legend would help. Better: a tooltip on the cell that explains "Good = PLC responded with valid data, Bad = PLC didn't respond, Uncertain = response was stale or partial."

**05-6. PRAISE — Refresh selector: `5 s | 15 s | 30 s | 1 min | 5 min`.** The minimum is 5s, which the draft note correctly identifies as the safe floor. Good.

**05-7. CONFUSING — DRAFT note in the wireframe says "The minimum poll period is 5 s. Sub-5s polling is intentionally not exposed here..." but there's no actual safeguard visible in the UI.** As an operator, I'd want to know that 5s is a floor *before* I try to change it. Either disable 1s / 2s options in the selector, or add a hint "5s minimum — lower values are restricted to protect PLC CPU." Also, the Settings → Advanced page has a "Allow sub-5s polling on Monitor (not recommended)" toggle mentioned in this DRAFT but not visible in the settings I read on page 09. **Verify that toggle exists on the real Settings page; if not, either add it or remove this draft.**

**05-8. CONFUSING — `⏸ Pause` button is the primary action on this screen.** Pause *what*? Polling? The display? The wireframe isn't clear. Tooltip: "Pauses live value updates. Sparkline and history will not grow. Click Resume to continue."

**05-9. CONFUSING — `Clear history` button.** Clears the local trend buffer? Clears the watch list? Clears persistent history (page 07)? All three? As an operator, "Clear history" with no confirmation could mean losing hours of trend data. Add a hint, and add a confirmation dialog: "Clear the 360 buffered samples? (Saved scan history on the History tab is not affected.)"

**05-10. CONFUSING — `Export values to CSV` button in the bottom-right.** As an operator, this is a duplicate of the Export tab (page 06). Two ways to do the same thing isn't bad, but the button doesn't say *what range* it exports: current visible watch list? All-time buffered samples? Just the 60-sample trend window? Tooltip required.

---

## 06-workspace-export.html

**06-1. CONFUSING — The "Source" radio has three options but "Selected tags only" is permanently disabled.** The hint says `(0 selected)` — so the disable is because nothing is selected on this screen. As an operator, "Selected tags only" implies I should select tags *somewhere* (presumably Browse) and then come back to Export. The workflow isn't documented. Add a one-line hint under the disabled radio: "Select tags in the Browse tab first, then return here."

**06-2. CONFUSING — "Last scan from history" is shown with `(148 tags)` but the hint doesn't say where that came from.** I assume it's the most recent scan from page 07 (History), but the radio label doesn't say "from the History tab." Be explicit: "Last saved scan (from the History tab) — 2026-06-15 14:22:07, 148 tags."

**06-3. CONFUSING — "Formats" checkboxes: all three are checked by default.** As an operator, I might want only one. The default of "all three" is a surprise: I clicked `Export` and now I have three files. Either:
   - Default to only Excel (the most common format) and require the operator to opt into JSON/XML, or
   - Add a quick "Select all / Select none" affordance, or
   - Show a confirm dialog: "Export 3 formats (xlsx + json + xml)?"

**06-4. CONFUSING — "Excel (.xlsx) — one sheet per UDT, all tags flattened" vs "JSON — nested object preserving UDT structure" vs "XML — CIP-style tag path per element".** The descriptions are technically accurate but assume the operator knows what a UDT is and what "flattened" vs "nested" means. As an operator: "What do I do with each format?" Add a one-line "use this when…" hint for each:
   - **Excel**: "Use this for reports, audits, opening in Excel."
   - **JSON**: "Use this for web dashboards, scripts, or programmatic processing."
   - **XML**: "Use this for L5X-compatible tools, version control, or SCADA import."

**06-5. CONFUSING — `Output folder` defaults to `C:\Users\adamssc\Documents\PLC Toolkit\exports`.** That's a hardcoded user-specific path (matches Scott's username). For shipping to other operators at Continental, this default needs to use a relative path or `%USERPROFILE%`. Currently this looks like developer-specific sample data left in the wireframe.

**06-6. CONFUSING — `Filename` defaults to `CompressorSkidA_2026-06-16_1015` with hint "Auto-generated from PLC nickname + timestamp. Editable."** The hint on the Settings page (09) says the template is `{nickname}_{YYYY-MM-DD}_{HHmm}` — but the field is *pre-filled with the rendered template*, not the template itself. So if I edit the filename to `foo`, the template is unaffected. But if I want to change the *template* (e.g. add `{ip}`), I have to go to Settings. The relationship between this field and the Settings template is unclear. Add a one-line hint: "Default filename follows the template in Settings → Export. Edit this one to override for this export only."

**06-7. CONFUSING — DRAFT note: "When multiple formats are checked, do we write one file per format (...) or one zipped bundle?"** As an operator, I would expect a zipped bundle to be the default — I get one download, one place to look, no risk of leaving one file behind. Ship a zipped bundle by default with an opt-out for "separate files."

**06-8. BLOCKER — `Export` button has no confirmation, no "what's about to happen" preview, no progress indicator.** I click Export, and three files appear somewhere. As an operator, I want a small confirm like "Writing 3 files to `C:\Users\…\exports\`: CompressorSkidA_2026-06-16_1015.xlsx (1.2 MB est.), .json, .xml — Continue?" and a progress bar / spinner for large exports.

**06-9. MINOR — Status bar shows `Last export: 2026-06-15 14:23:02 → 3 files (4.1 MB)`.** Useful for the operator to verify the last export. Keep.

**06-10. CONFUSING — The "Source" radio's first option says "Current in-memory tag tree — 142 tags from this session's Re-discover".** What happens if I never clicked Re-discover? Does the in-memory tree still exist? As an operator I'd want to know: "If you haven't done a Re-discover yet, the in-memory tree is whatever was loaded when you connected." Add that as a hint.

---

## 07-workspace-history.html

**07-1. PRAISE — Tabular history with timestamp, duration, tag count, delta vs previous, size, source.** The columns are all things I'd want to know. Good data density.

**07-2. CONFUSING — "Delta vs. previous" column shows `+2 added (Pump_03.*)` and `+1 added (Compressor.Run)`.** This is great information, but the abbreviation `(Pump_03.*)` is jargon. As an operator: does the `*` mean "all children"? Add a tooltip or expand the hint: "Tags added since the previous scan — the wildcard means all members of that UDT."

**07-3. CONFUSING — "Source" column says `Re-discover` / `Scheduled` / `Manual`.** "Scheduled" implies there's a background scheduler, but the v1 TUI is a CLI tool. Does the v2.0 GUI have a scheduled scan feature? I don't see one mentioned anywhere. If "Scheduled" doesn't exist as a real source, remove the row. If it does, document it.

**07-4. BLOCKER — Per-row `Delete` button has no confirmation.** Each row has a `View | Export | Delete` action set. A misclick on Delete nukes a stored scan, and the operator has no way to recover it. Add a confirm dialog: "Delete scan #0042 (2026-06-15 14:22:07, 1.1 MB)? This cannot be undone." Same for bulk operations.

**07-5. CONFUSING — "Compare selected scans" button shows `2 of 42 selected` next to it.** As an operator, "compare" is vague. What does comparing two scans show me? The DRAFT note asks the same question. As an operator I'd want: "Show me a side-by-side list of tags that were added, removed, or whose values changed between the two scans." That's the obvious use case. Ship that.

**07-6. CONFUSING — `Refresh` button is far right with no hint.** Self-explanatory, but its purpose is unclear if the list is supposed to auto-refresh. Does it? Add a hint: "Re-reads the scan history from the database. Does not trigger a new scan." Or auto-refresh and remove the button.

**07-7. PRAISE — Status bar `History: 42 scans stored locally (this PLC)`.** Useful. Combined with the Settings → Retain history (days) = 90, I can plan when scans will roll off.

**07-8. CONFUSING — The History tab is marked with a `NEW` pill in gold.** As a first-time operator I don't know what "NEW" means relative to what. (I never saw v1.) It implies this is a new feature. If I'm an operator who has been using v1 for years, "NEW" tells me "this is the thing that changed" — which is fine. If I'm a new operator, "NEW" is meaningless. Either keep it (it works for upgrades) or remove it. The CSS comment says it should be removed 1–2 releases after GA. That's a policy decision; flagging it for the record.

---

## 08-workspace-diagnostics.html

**08-1. PRAISE — "Connection summary" + "Bandwidth" + "Recent activity log" is a strong operator-friendly layout.** This is the screen I'd open when something looks wrong. Good.

**08-2. CONFUSING — Driver shown as `pycomm3.LogixDriver` and `pycomm3 1.2.10`.** See global finding G5. Must read `pylogix.PLC` and `pylogix <version>` for v2.0.

**08-3. CONFUSING — "PLC identity" shows `1756-L82E / v32.011`.** A first-time operator may not know what a `1756-L82E` is. Add a tooltip: "Catalog number and firmware revision of the connected processor (ControlLogix 5580, v32 firmware)."

**08-4. CONFUSING — "Round-trip latency 4.1 ms (avg) / 11 ms (max)".** Is 11ms good or bad? As an operator, a number without context is just a number. Add a hint: "Healthy range is 1-20ms; >100ms indicates network or PLC load issues." Or color-code the cell: green for <50ms, amber for 50-100ms, red for >100ms.

**08-5. CONFUSING — "Bytes in (session) 1,842,113" and "Bytes out (session) 224,580".** Why is "in" 8x "out"? As an operator I don't know. Tooltip: "Cumulative bytes since connection opened. Reads are larger than writes because tag values are returned in full." Or just label the column "Bytes read / Bytes written" — clearer than in/out.

**08-6. CONFUSING — "Writes / sec 0".** This is reassuring, but the column existing at all implies writes are a feature. As an operator, the v2.0 scope is read-only, so why is "Writes / sec" on the Diagnostics page? It's a v2.1-readiness placeholder. Either remove the row, or add a hint: "Writes are not yet supported in v2.0 (planned for a future release)."

**08-7. CONFUSING — `Re-test connection` button is the primary action on this screen.** As an operator, I'd expect a "Re-test" to fire the same test as the New Connection test (page 02) and show me the same result panel. The wireframe doesn't show what happens after a click. As a first-time operator, I'd like a hint: "Re-runs the connection test (same as New Connection → Test connection)."

**08-8. CONFUSING — `Copy diagnostics to clipboard` button.** What gets copied? The DRAFT note asks the same question. As an operator, I'd want a plain-text dump: timestamp + connection summary + bandwidth + the visible log entries. That's what I'd paste into a ticket.

**08-9. CONFUSING — `Clear log` button has no confirmation.** "Log" could mean the in-memory recent activity log, or the on-disk session log. As an operator, clearing the wrong one could lose forensic data. Add a confirmation: "Clear the 6 in-memory log entries? (On-disk session log is not affected.)"

**08-10. CONFUSING — `Showing 6 of 6 events. Log retained for 24h.`** 24 hours is short. If a tech is investigating an issue from yesterday, the log is gone. This should be configurable in Settings (it is — see 09 — but the default of 24h is short). Consider bumping the default to 7d.

**08-11. CONFUSING — Activity log shows `get_plc_info()` returning `ERROR` (line 129).** As an operator, my eye goes to the red ERROR cell, and the explanation is in the `Action` column as a code call. As an operator I don't read `get_plc_info()`. Add a friendlier description column: `Initial handshake with PLC (catalog + firmware)` or label the column "Action" with a `(in plain English)` hint.

**08-12. PRAISE — Status bar `Log path: %APPDATA%\PLCToolkit\logs\session_2026-06-16_10-10-33.log`.** Tells me exactly where to look if I need to attach a log to a support ticket. Good.

---

## 09-settings.html

**09-1. CONFUSING — Settings opens as a modal over a dimmed Connection Manager.** Same pattern as page 02 and 03. Consistent. Good. But: the modal is 760px wide with a max-height of 70vh and overflow auto, which means on a 1280px screen the bottom of the modal is below the fold and the operator must scroll *inside* the modal. As an operator, that's not obvious. The page is a long form, not a popup. Consider making it a full-page screen (like page 09 is on the index but a full page, not a modal).

**09-2. CONFUSING — Settings are organized into six sections: Connection, Polling & display, Discovery, Storage, Export, Advanced.** Good organization. But as a first-time operator, "Discovery" is the third section and "Storage" / "Export" / "Advanced" are technical. The naming is fine, but the *first* section an operator will care about is probably "Connection" and the "Polling & display" defaults (5s poll, 60-sample trend). Make those two prominent.

**09-3. CONFUSING — "Default connection timeout (s) 5" with hint "Used when no per-connection value is set."** This is the *default* used when a per-connection value isn't set. As an operator, I just created a new connection on page 02 with timeout=5 in the advanced section. If I change this default to 10, does the per-connection value (5) stay 5, or does it update? Tooltip: "Default applied to new connections. Existing connections keep their saved value."

**09-4. CONFUSING — "Connect retries 3" and "Retry delay (ms) 500".** Both are number inputs with no hint. As an operator: 3 retries and 500ms delay means up to 1.5s of retrying on a failed connect. That seems reasonable, but the *meaning* of the numbers isn't documented. Add hints: "How many times to retry if the first connection attempt fails" and "How long to wait between retries."

**09-5. CONFUSING — "Auto-reconnect on dropped session" is checked by default.** That's good. As an operator I want this on. But the checkbox is in the same section as timeout/retry; the relationship between "retries" and "auto-reconnect" isn't clear. Are they the same thing? Hint: "Re-opens the CIP session automatically if it drops during normal use. Different from Connect retries (which only apply at initial connect)."

**09-6. CONFUSING — "Default port 44818" with no hint.** Same finding as page 02. EtherNet/IP port. Add a hint.

**09-7. CONFUSING — "Verify IP is reachable before opening CIP session" is checked by default.** This is a performance-vs-reliability tradeoff. As an operator, I want reliability, but I want to know what I'm paying for it. Hint: "Adds a quick ICMP/ARP check before opening the CIP session (~50ms). Disable if your network blocks ICMP."

**09-8. CONFUSING — "Default network" and "Default CIDR" under "Discovery defaults".** These are advanced-ish fields but they sit in the middle of the Connection section, which is the first section. As a first-time operator, I won't touch them, but they'll see them. Move them under "Discovery" (the third section), or label them "(advanced)" so they read as opt-in.

**09-9. CONFUSING — "Default poll rate" 5s, with hint "Minimum 5 s. Sub-5s polling against a CompactLogix/ControlLogix is restricted."** Good hint, matches the Monitor tab's draft note about a Settings → Advanced → "Allow sub-5s polling" toggle. **Verify that toggle exists.** If it doesn't, the DRAFT on page 05 promises a feature that isn't there. Either ship the toggle or remove the promise.

**09-10. CONFUSING — "Use symbolic addressing (CIP path = tag name) — pylogix default; always on" is shown as a checked disabled checkbox.** As an operator, the label "symbolic addressing" is opaque. A one-line hint would help, OR — better — don't show this setting at all if it's always on. The CSS comment in the file is good context for engineers, but operators don't need a setting they can't change. The `v2.0 scope is read-only on symbolic paths` is an implementation detail, not a user choice.

**09-11. CONFUSING — "BOOL display: 0 / 1 | FALSE / TRUE | Off / On".** Good. But the hint "Default 0/1 matches the Studio 5000 tag display." is *also* a setting for BOOL tags specifically. Is there a parallel setting for REAL? DINT? The wireframe is silent. If BOOL is the only one with display options, that's fine; if other types have display options that should match, they're missing. (AGENTS.md says "Display REAL as decimal" is forbidden in v2.0 — so REAL is correctly omitted. DINT/STRING are also out of scope. **OK, this is correct.**)

**09-12. CONFUSING — "Default trend window (samples) 60".** As an operator, "samples" is jargon. Tooltip: "How many data points to keep in the sparkline. 60 = 60 polls. At 5s poll, that's 5 minutes of history."

**09-13. CONFUSING — "Probe concurrency 50" with hint "Max parallel probes during a subnet scan. Subnet scan uses our own loop, not pylogix's broadcast."** As an operator, "concurrency" is programmer-speak. Also, the "50" is arbitrary. Hint: "How many hosts to probe at once. 50 is a reasonable default; lower if your network or PC struggles during a scan." Also, the second sentence is engineering context, not user help. Strip it.

**09-14. CONFUSING — "Per-probe timeout (ms) 500".** As an operator, "per-probe" and "ms" are both jargon. Hint: "How long to wait for a single host to respond before giving up on that host (not on the whole scan). 500ms is a good default for LAN; raise to 2000 for slow networks."

**09-15. CONFUSING — "Remember last interface between sessions" is unchecked by default.** As an operator, I'd want this on. Hint: "If you usually scan the same network, the dialog will open with your last interface selected." (Worth defaulting to checked for typical use.)

**09-16. CONFUSING — "Database path" and "Scan archives" with hardcoded `%APPDATA%` paths and a `Browse…` button.** As an operator, the `Browse…` button is the only thing I'd touch here. The path is fine as a default but the field is editable — which means I could type a path that breaks the app. Add a hint: "Where scan history and connection settings are stored. Change only if you need to move storage to a network share."

**09-17. CONFUSING — "Retain history (days) 90" with "Auto-prune scans older than retention window" checked.** Good. As an operator, 90 days is a reasonable default. But: does auto-prune run on every launch, on a schedule, or when the database size hits a limit? Add a hint: "On each launch, scans older than this are deleted (if auto-prune is on)."

**09-18. CONFUSING — "Encrypt local database (SQLCipher) — planned for v2.1; pylogix does not yet support SQLCipher".** This is shown as an unchecked checkbox. As an operator, I see an unchecked box and assume I can check it. But the hint says it doesn't work yet. Two options:
   - Disable the checkbox until the feature ships, OR
   - Remove the row entirely from the shipped UI (it's a v2.1 placeholder).

   Right now it's a footgun: an operator who checks it will discover later that the encryption isn't actually happening.

**09-19. CONFUSING — "Default export folder" with hardcoded `%USERPROFILE%\Documents\PLCToolkit\exports`.** The New Connection and Export pages also reference the user-specific `C:\Users\adamssc\Documents\PLC Toolkit\exports`. Three different places to set the export folder (modal, export page, settings) is one too many. Consolidate: the export folder lives only in Settings, and the Export page reads it from there. The wireframe has it on both the Export page (with `Browse…`) AND in Settings (with `Browse…`) — that's the bug.

**09-20. CONFUSING — "Filename template `{nickname}_{YYYY-MM-DD}_{HHmm}`" with hint "Tokens: {nickname}, {ip}, {slot}, {YYYY-MM-DD}, {HHmm}".** As an operator, the tokens are discoverable but I'd want a `Live preview:` line below the field that shows what the rendered filename will look like. Without it, I'm guessing what `{HHmm}` produces (`HHmm` = hour + minute, no separator, no AM/PM — but I have to read the spec to know). Preview would close the loop.

**09-21. CONFUSING — "Excel by default", "JSON by default", "XML by default" checkboxes, all checked by default.** This duplicates the per-export checkboxes on the Export page (06). Two places to set the default formats is one too many. Consolidate: the default formats live in Settings, and the Export page starts with the Settings defaults but allows per-export override.

**09-22. CONFUSING — "Open output folder when export finishes" — unchecked by default.** That's fine. As an operator, I'd want this checked. Hint: "When an export finishes, opens the output folder in Windows Explorer so you can see the new files immediately."

**09-23. CONFUSING — "Log level: DEBUG | INFO | WARNING | ERROR".** As an operator, I don't know what `DEBUG` vs `INFO` means. Hint: "How much detail to write to the diagnostic log. INFO is recommended for normal use; DEBUG is verbose and may slow the app on a slow network."

**09-24. CONFUSING — "Log file path" with no `Browse…` button.** The Database path and Scan archives fields both have Browse buttons; the Log file path doesn't. Inconsistent. Add a Browse button.

**09-25. CONFUSING — "UI theme: Dark (default) | Light" is in the Advanced section.** This is a basic user preference, not an advanced setting. Move it to the top of Settings, or to a "General" section. The DRAFT note admits "UI theme wasn't in the original settings list; included under Advanced as a placeholder." This needs a real home.

**09-26. CONFUSING — "Reset to defaults" button has no confirmation.** One click and all my settings are wiped. As an operator managing multiple PLCs with custom timeouts, that's a lot of rework. Add a confirmation: "Reset all settings to factory defaults? This will not affect your saved PLC connections."

**09-27. PRAISE — `Save` is the primary button, `Cancel` is secondary, `Reset to defaults` is a separate action.** Good hierarchy.

---

## 10-help.html

**10-1. BLOCKER — Help page is a stub.** The page openly says "Not yet implemented — flagged for v2.1." As an operator, I click `? Help` expecting an answer to my question, and I get "this isn't built yet, check the README." For a SCADA tool, help is not optional. **This is a blocker for shipping to operators.** A minimum-viable help page with: troubleshooting for "Can't connect" (check IP, check subnet, check PLC power), "Test connection failed" (CIP error decoder, timeouts), and a glossary (UDT, BOOL, REAL, CIP path) would cover 80% of operator questions.

**10-2. CONFUSING — "The in-app help system is intentionally not built for v1. This screen is a placeholder so the `? Help` icon in the top bar has somewhere to go without throwing an error."** The wireframe admits this is a non-functional placeholder. The `? Help` button takes the operator to a dead end. As an operator, this is the *most* important screen when something is broken, and it's blank. Ship a minimum-viable help page in v2.0, or remove the `? Help` button until the page is real.

**10-3. CONFUSING — "For the v1 release, the README in the install directory will cover:" followed by a list.** The README is on disk somewhere. As an operator, I don't know where. Either (a) link to it: `Open the README at C:\Program Files\PLCToolkit\README.md`, or (b) embed the README's content in the help page.

**10-4. CONFUSING — Status bar says `Help is a stub.`** That phrasing will land in a screenshot the day it ships. Replace with something more professional: "Help is a placeholder. In-app help is coming in v2.1."

**10-5. MINOR — The `← Back to Connection Manager` button is the only actionable thing on the page.** As an operator, this confirms the navigation works but doesn't help me solve my problem. Add a "Need help now? Email scada-support@…" or similar.

---

## Top 5 issues to fix before v2.0 ships

Ranked by severity (blockers first, then user-impacting confusion, then polish).

**1. [BLOCKER] Help page is a stub (10-help.html).** Operators hit `? Help` when something is broken, and the page says "not yet implemented." For a SCADA tool, help is critical-path. Ship a minimum-viable help page in v2.0 with: connection troubleshooting (IP wrong, PLC unreachable, CIP path errors), a glossary of every acronym used in the UI (UDT, BOOL, REAL, DINT, CIP path, port 44818, slot), and links to the README and a support email. Defer the full help system to v2.1, but the current "this is a stub" page cannot ship to operators.

**2. [BLOCKER] Destructive actions have no confirmation.** Found on three pages:
   - Page 01: `Remove selected` deletes a saved connection with no confirm.
   - Page 07: `Delete` on each scan row with no confirm.
   - Page 09: `Reset to defaults` with no confirm.
   - Page 04–08: `Disconnect` button with no confirm (operator can lose a Monitor session with one click).
   - Page 05: `Clear history` with no confirm.
   - Page 08: `Clear log` with no confirm.
   Every destructive action needs a confirmation dialog with the action spelled out ("Delete scan #0042 (2026-06-15, 1.1 MB)? This cannot be undone."). For an operator, "undo" support on bulk actions is also strongly recommended.

**3. [BLOCKER] `Driver: pycomm3.LogixDriver` and `Driver version: pycomm3 1.2.10` on the status bar (page 04) and Diagnostics page (08).** This is the v1 driver name, and v2.0 is pylogix-only by project rule. When an operator pastes their diagnostics into a support ticket, the wrong driver name will be reported and the support tech will be misled. Replace with `pylogix.PLC` and `pylogix <version>` on both pages.

**4. [CONFUSING] DRAFT notes are visible in the shipping UI.** Every page except Help has visible `[DRAFT: question for user]` blocks (page 04 alone has three of them). As an operator, these read as developer scaffolding that escaped. Either strip them entirely before shipping, or hide them behind a "Show design notes" toggle that defaults off. This is the single biggest "first impression" issue — an operator opening the app for the first time will see "DRAFT" boxes and assume the app is unfinished.

**5. [CONFUSING] UDT bulk-add and write-tag distinction are not handled safely on the Browse tab (page 04).** The `[+]` button on a UDT row (e.g. `Pump_01`) silently adds all leaf members to the watch list (per the right-click menu DRAFT note). And `Pump_01.StartCmd` / `Pump_01.StopCmd` (BOOL command tags) have the same `[+]` affordance as read-only tags like `Pump_01.Speed`, with no visual distinction. The first is surprising behavior; the second is a future footgun if write-back is ever added (deferred to v2.1 per AGENTS.md, but the lack of visual distinction in v2.0 means it'll be one click away). For the bulk-add: add a confirm dialog showing "Add Pump_01 to monitor? (8 leaf tags will be watched)" or visually distinguish `[+8]` on UDT rows. For write tags: add a small "cmd" or "R/W" pill next to command tags, or grey out `[+]` on write tags with a tooltip "Write tags are not supported in v2.0 (read-only monitoring)."

**Honourable mentions (not in the top 5 but worth fixing):**
- The three "Scope" modes on page 03 need one-line descriptions on the labels themselves, not in a draft note below.
- The Export page (06) should ship with a confirm-and-progress flow ("Writing 3 files to … — Continue?" + spinner).
- Settings (09) duplicates the export folder and default formats with the Export page (06) — pick one place to set them.
- The right pane of the Browse tab (04) is empty placeholder text. As the operator's main view post-connect, it should show the current connection summary, the selected tag's value, or a "Click a tag to see its value" coaching message with examples.
- The "5d ago" connection on page 01 is visually identical to the live ones. Add a status dot or column to indicate reachability.
