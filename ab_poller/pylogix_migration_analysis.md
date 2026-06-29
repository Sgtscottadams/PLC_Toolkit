# pylogix Migration Cost Analysis — PLC Toolkit

**Target file:** `ab_poller/plc_toolkit_consolidated.py` (779 lines, pycomm3 1.2.16)
**Candidate replacement:** pylogix 1.1.5 (dmroeder/pylogix, Apache-2.0)
**Date of analysis:** 2026-06-16

---

## 1. Version + Maintenance Status

### pylogix
- **Latest PyPI version:** `1.1.5`, uploaded **2026-02-23 21:24:53 UTC** — https://pypi.org/project/pylogix/#history
- **Last GitHub push:** `2026-05-18T15:05:32Z` (`pushed_at` from repo API) — https://api.github.com/repos/dmroeder/pylogix
- **Repo state:** `archived: false`, `disabled: false`, default branch `master` — same API call
- **Issue counts (search API):** 14 open, 164 closed — https://github.com/dmroeder/pylogix/issues
- **Stars/forks/subs:** 712 / 200 / 75 — same API call
- **Maintenance signal:** Active. 13 PyPI releases in 2024–2026 alone (1.0.0 → 1.1.5), and the project is wired to a Discord support channel (see `README.md` of repo). **No "looking for maintainers" notice** in the README or anywhere in the repo (verified: the README prominently displays the maintainer `dmroeder` as author; the only "WARNING" is about an unrelated *notpylogix.com* scam site, not maintenance).

### pycomm3 (for reference)
- **Latest PyPI version:** `1.2.16`, uploaded **2022-09-16T00:25:38Z** — https://pypi.org/project/pycomm3/
- **Repo:** https://github.com/ottowayi/pycomm3
- **Maintenance signal:** The maintainer (`Ian`) posted an official notice on **2025-12-22** in issue #333 "Project Status":
  > *"this library is no longer being actively developed… issues are unlikely to be addressed and new updates should not be expected."*
  Source: https://github.com/ottowayi/pycomm3/issues/333
- **README header** (master branch, line ~21) contains: `**⚠️ NOTE:** pycomm3 is no longer actively developed`

**Bottom line:** pylogix is currently the more actively maintained project. pycomm3 is frozen at 1.2.16.

---

## 2. API Parity Table (pycomm3 calls used by the toolkit → pylogix)

| # | pycomm3 call (current usage) | pylogix equivalent | Notes / source |
|---|---|---|---|
| 1 | `LogixDriver(ip, slot=slot, timeout=10, init_tags=False)` + `.open()` | `PLC(ip_address, slot, timeout, Micro800, port)` (no explicit `open()`; first I/O call auto-connects via `Connection.connect()`) | `pylogix/eip.py:42` `def __init__(self, ip_address="", slot=0, timeout=5.0, Micro800=False, port=44818)`. Usage idiom is the `with` block. No `init_tags` flag — pylogix auto-discovers types lazily (`self.KnownTags`). |
| 2 | `driver.get_plc_info()` → `dict` with `plc_name`, `revision.{major,minor}` | **No direct equivalent.** `PLC.GetDeviceProperties()` returns a `Device` object with `IPAddress, Vendor, DeviceID, ProductCode, Revision (str "M.m"), ProductName, SerialNumber, State` — but **not** `plc_name`/program-name. `Revision` is a single string, not a dict. Source: `eip.py:258-265`; `lgx_device.py:91-101`. | The toolkit's `plc_info['plc_name']` field has no 1:1 mapping. Closest substitutes: `Device.ProductName` (e.g. `"1756-L83E/B"`) and the program name from `GetProgramsList()`. |
| 3 | `driver.get_tag_list()` → list of dicts (`tag_name`, `data_type`) | `PLC.GetTagList(allTags=True)` → `Response.Value` is `list[Tag]`, each with `TagName, DataType, DataTypeValue, Struct, Array, Size`. Source: `eip.py:168-183`, `lgx_tag.py:14-32`. | Naming changes: `tag_name` → `TagName`, `data_type` → `DataType` (capitalised). |
| 4 | `driver.get_tag_list(program=prog_name)` inside a loop after `driver.read('PROGRAM')` | `PLC.GetProgramTagList("Program:Name")` returns `Response.Value` containing `list[Tag]`. `PLC.GetProgramsList()` returns just program names, removing the need to read the `PROGRAM` tag manually. Sources: `eip.py:185-209`, `eip.py:211-233`. | Behavioural change: pylogix does the program list internally; the toolkit's manual `read('PROGRAM')` trick is obsolete. |
| 5 | `driver.get_tag_info(tag_name)` → nested dict with `data_type.internal_tags` (UDT recursion) | **No public per-tag equivalent.** pylogix builds a UDT cache in `self.UDT` / `self.UDTByName` only as a side effect of `GetTagList()` (internal method `_get_udt` at `eip.py:866-967`). The `UDT` class has `Fields` (list of `Tag`) and `FieldsByName` (dict). Source: `eip.py:177-183`, `eip.py:866-967`, `lgx_tag.py:103-130`. | The toolkit's `_parse_structure_def` recursion in `plc_toolkit_consolidated.py:274-299` relies on `tag_def['data_type']['internal_tags']` — that exact shape does **not** exist in pylogix. We'd have to walk `plc.UDTByName[tag.DataType].Fields[].Fields…` ourselves. There is an **open issue #125 "Scanning Members of UDT"** since 2020-04-20 (https://github.com/dmroeder/pylogix/issues/125) where the maintainer has not added a public accessor. |
| 6 | `driver.read(tag)` → response `.tag, .value, .type, .error` | `plc.Read(tag)` → **single** `Response` object with `.TagName, .Value, .Status` (a string like `"Success"` or a CIP error string). For *lists* of tags, returns `list[Response]`. Source: `eip.py:111-132`, `lgx_response.py:20-26`, `lgx_response.py:54-105` (the CIP error code table). | Field renames: `tag→TagName`, `value→Value`, `type→DataType` (when known), `error→Status` (CIP error string, not None/str). Crucially, **a single-tag read does NOT return a list of Tag objects** as the task brief assumed — it returns one Response. The list form only triggers when you pass a `list` of tags. |
| 7 | `CIPDriver.discover()` / `CIPDriver.list_identity(path)` — UDP/TCP broadcast on 44818 (planned, not yet coded in the project) | `PLC.Discover()` → `Response.Value` is `list[Device]` (from `Connection.discover()`). Source: `eip.py:235-248`, `lgx_comm.py:826-885`. Same wire protocol (CIP service `0x63` ListIdentity, UDP to `255.255.255.255` on `parent.Port`, default 44818). | **Identical protocol, identical limitations.** No subnet confinement — iterates `socket.getaddrinfo(hostname, None)` for each IPv4 address and broadcasts. There are **two open issues** about this: #93 "Scan PLCs on Another Subnet" (2019-12-12) and #111 "How to discover devices in all Vlans?" (2020-03-10), neither addressed. |

---

## 3. Discovery Support — UDP/TCP, subnet confinement

pylogix `Discover()` is **UDP broadcast**, identical wire format to pycomm3:

`pylogix/lgx_comm.py:826-885` (quoted verbatim, key lines):
```python
def discover(self, parse_procedural_parameter):
    devices = []
    request = self._build_list_identity()
    # get available ip addresses
    addresses = socket.getaddrinfo(socket.gethostname(), None)
    for ip in addresses:
        if ip[0] == 2:  # IP v4
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind((ip[4][0], 0))
            s.sendto(request, ('255.255.255.255', self.parent.Port))
```
…and `lgx_comm.py:887-911` builds `cip_service = 0x63` (the standard CIP ListIdentity).

**Subnet confinement: NO.** pylogix always broadcasts to `255.255.255.255` from every IPv4 interface on the host. There is no `broadcast_address` parameter (unlike pycomm3's `CIPDriver.discover(broadcast_address="…")` at `pycomm3/cip_driver.py:202-208`). Open issues #93 and #111 confirm this is a known limitation with no fix in the 1.1.5 release.

---

## 4. Read Semantics

**pylogix `Read()` returns a `Response` object for a single tag** (not a list):

`pylogix/eip.py:111-132` (signature):
```python
def Read(self, tag, count=1, datatype=None):
    if isinstance(tag, (list, tuple)):
        ...
        return [self._read_tag(...)]   # list form
    else:
        return self._read_tag(tag, count, datatype)   # single Response
```

`pylogix/lgx_response.py:18-26`:
```python
class Response(object):
    def __init__(self, tag_name, value, status):
        self.TagName = tag_name
        self.Value = value
        self.Status = self.get_error_code(status)
```

**Error signalling** (verified): pylogix does **not** raise on read failure. It populates `Response.Status` with the CIP error string (e.g. `"Success"`, `"Path destination unknown"`, `"Invalid parameter value"`). The `Response` is always returned. The full CIP error table is in `lgx_response.py:54-105`. Source confirmed.

This is a notable semantic difference from pycomm3, where `Tag.error` is `None` on success and a `RequestError` may also be raised depending on configuration. Migration must convert `if result.Status != "Success":` checks in place of the existing `if result.error:` checks.

---

## 5. UDT (User-Defined Type) Introspection — The Hard Question

**Verdict: pylogix DOES expose UDT members, but not via a per-tag `get_tag_info()`-style accessor.** The GUI's "drill into UDT" feature is **survivable** but requires a custom traversal.

What pylogix actually does:

1. `PLC.GetTagList(allTags=True)` at `eip.py:168-183` internally calls `_get_tag_list()` then `_get_udt()`. After this call, the cache is built:
   - `plc.UDT` — `dict[instance_id: int, udt: UDT]`
   - `plc.UDTByName` — `dict[type_name: str, udt: UDT]`
   - `plc.TagList` — `list[Tag]` where each `Tag.DataType` is now resolved to a UDT name string when applicable.

2. `_get_udt()` at `eip.py:866-967` walks every struct tag, calls `_get_template_attribute()` (CIP service 0x03 / class 0x6c) and `_get_template()` (CIP service 0x4c / class 0x6c), then constructs `UDT()` objects whose `Fields` list contains `Tag` records with `TagName, DataType, DataTypeValue, Array, Struct, Size, Bytes` etc. (`lgx_tag.py:103-130`).

3. There is **no per-tag accessor**. The maintainer's answer on issue #125 (2020-04-20, https://github.com/dmroeder/pylogix/issues/125#issuecomment-817113994) was that UDT member walking is "not in pylogix, but pycomm3 has it."

**Migration impact on `plc_toolkit_consolidated.py:274-299` (`_parse_structure_def`):** The function currently consumes `tag_def['data_type']['internal_tags']` returned from `get_tag_info()`. That exact shape does not exist in pylogix. We will need to rewrite `_parse_structure_def` to instead look up `plc.UDTByName.get(tag.DataType)` and walk `udt.Fields` + nested `UDT` references.

The fields on pylogix `Tag` are sparser than pycomm3's (no `internal_tags` recursion tree, no `dim`, no `radix`, no `external_access`). For the GUI's purpose — display tree + read values — this is fine.

---

## 6. Multi-PLC and Threading

**Multiple connections from one process: YES, supported, and recommended by the maintainer.** From issue #105 comment by `dmroeder` (https://github.com/dmroeder/pylogix/issues/105):
> *"I would create an instance of the driver for each PLC… `plc1 = PLC('192.168.1.10')`, `plc2 = PLC('192.168.1.100')`"*

**Thread-safety caveat: YES, identical to pycomm3.** From `pylogix/docs/Documentation.md:73-77` (verbatim):
> *"3. When using with threads, be sure to create an instance for each thread, as opposed to sharing the instance between threads"*

I searched `pylogix/eip.py` and `pylogix/lgx_comm.py` for any `threading.Lock`, `threading.RLock`, `Lock()`, or `RLock()` — **none found** (`grep -n "thread\|Lock\|lock" /tmp/eip.py /tmp/lgx_comm.py` returned only a few unrelated substring matches in comments/strings). So there is no internal locking; the "no shared instances across threads" rule is enforced purely by convention.

Open issue #188 "Correct way to maintain a connection to a PLC" (2021-11-23, still open) notes EXCP 0300 errors when opening/closing repeatedly — directly relevant to a future PySide6 GUI that may open a connection per dialog. Workaround: keep one long-lived `PLC()` instance per worker thread.

---

## 7. Migration Cost Estimate

Assuming **one experienced Python developer**, working on `plc_toolkit_consolidated.py` (779 lines, the only file that touches `pycomm3` — verified with `grep "pycomm3" /tmp/*.py` → only line 19 imports it):

### 7a. Code changes in `plc_toolkit_consolidated.py`

| Area | Lines to touch | Effort |
|---|---|---|
| **Import + connection setup** (`PLCToolkit.connect`, lines 19, 186-210) | Replace `LogixDriver` with `PLC`; drop explicit `.open()`; raise `SocketTimeout` to 10s; close via `with` block or `.Close()` | 1 h |
| **`_parse_structure_def` rewrite** (lines 274-299) | Recurse over `plc.UDTByName[tag.DataType].Fields` instead of `tag_def['data_type']['internal_tags']`; map pylogix `Tag` fields (no `dim`, `radix`, `external_access`) into the existing internal `{_data_type_, members}` dict shape so the downstream Excel/JSON/XML code (lines 349-435) keeps working unchanged | 4–6 h (the only non-trivial piece) |
| **`discover_tags` rework** (lines 219-272) | Replace the `read('PROGRAM')`+`get_tag_list(program=…)` loop with `GetProgramsList()` + `GetProgramTagList(p)`; resolve each `Tag.DataType` to its UDT name for the structure dump | 2 h |
| **PLC-info dict mapping** (lines 196-201, 686-691, `update_plc_data`) | Map pylogix `Device.ProductName` → `plc_name`, parse `Device.Revision` (e.g. `"30.11"`) into `{major, minor}` to preserve the existing dict contract | 1 h |
| **Read-result error handling** (lines 530, 675) | Change `if result.error:` → `if result.Status != "Success":`; field renames `result.tag → result.TagName`, `result.value → result.Value`, `result.type → result.DataType` (or `result.Value`'s Python type as a fallback) | 1 h |
| **Discover() feature** (new, per the planned task) | Implement a `subnet_discovery()` method using `PLC.Discover()` and present `Device.IPAddress, ProductName, Revision, Vendor`. If we want subnet confinement we'd need to implement our own UDP socket — pylogix won't do it (issue #93). | 2–4 h |
| **Misc renames + testing on a real PLC** | variable renames, import block, README | 1 h |

**Subtotal: ~12–16 person-hours** for code changes in the TUI module.

### 7b. Testing effort (we have no tests today)

For a comms layer of this size (10 public methods, 7 of which touch the wire), I'd budget **8–12 unit tests + 3–5 integration tests**. Specifically:

| Test type | Examples | Count | Effort |
|---|---|---|---|
| Pure unit (mocks) | `_parse_structure_def` with synthetic UDT/Tag trees (UDT member present, UDT member missing, member with `Array`, member with `DataTypeValue` not in `UDTByName`, empty `UDT` cache) | 6 | 4 h |
| Pure unit (mocks) | `_find_case_insensitive_tag` — base + nested, miss case | 4 | 1 h |
| Pure unit | CSV/XLSX/JSON/XML exporters on canned `self.tags` dict | 4 | 2 h |
| Pure unit | `DatabaseManager` upsert idempotency | 2 | 1 h |
| **Integration** (requires physical or emulated PLC) | connect, get_plc_info, GetTagList, GetProgramTagList, GetProgramsList, Discover, Read fundamental types, Read UDT member, write-untouched round-trip | 5 | 6 h |

If we add a CI matrix that uses **RSEmulate 5000** (pylogix has explicit Emulate support: https://github.com/dmroeder/pylogix/blob/master/docs/Emulate.md), we can run the integration suite unattended. Add 2 h for harness wiring.

**Subtotal: ~16 person-hours** to add a meaningful test suite.

### 7c. Risk / what pylogix does NOT give us

1. **No public per-tag UDT accessor.** Workaround: walk `plc.UDTByName` ourselves. The shape is flat (`UDT.Fields` is a `list[Tag]`, no nested dict tree). If the GUI later wants to show UDT member *descriptions* or `external_access` attributes, pylogix lacks those — pycomm3 has them (`Tag.dim`, `Tag.radix`, `Tag.external_access` in `pycomm3/custom_types.py`). **Risk: medium.**
2. **No automatic `init_tags` style bulk discovery.** pylogix lazily learns types on first read via `KnownTags`. For our discovery workflow (which scans hundreds of tags at startup), this adds N extra CIP round-trips. Workaround: call `Read([...])` in batches. **Risk: low–medium (latency only).**
3. **No case-insensitive tag lookup.** pylogix's `Read` is case-sensitive. Our existing `_find_case_insensitive_tag` helper (lines 456-498) already operates on the cached `self.tags` dict, so this is a non-issue **only** if we cache the tag list after `GetTagList` (which we already do). **Risk: low.**
4. **Discover has no subnet confinement.** If the SCADA shop spans VLANs, the planned discovery feature will need a custom UDP socket that binds to a specific interface. **Risk: medium for the planned discovery feature only.**
5. **No type validation on write.** pylogix trusts you to send the right type; pycomm3 has a richer `data_type` system. The current toolkit does not write, so this is moot.
6. **MicroPython builds only list classifiers `Python :: 2.7, 3.6`.** Verified on PyPI metadata. The 1.1.5 wheel is `py2.py3-none-any.whl` (https://pypi.org/project/pylogix/1.1.5/) so it will install on 3.11, but the project does not advertise 3.10/3.11/3.12 compatibility. **Risk: low** (no observed incompatibilities; the code uses `socket.AF_INET`, `struct`, `math.ceil`, basic introspection — all stable across versions).
7. **UDT detection prints to stdout on parse failure.** `_get_udt` at `eip.py:895` calls `print("Received invalid template attribute for", u.TagName)`. Annoying in a TUI but harmless.

---

## 8. Honest Verdict

**Recommend migrating to pylogix**, with one caveat.

The facts:

1. **pycomm3 is officially dead.** Maintainer's own 2025-12-22 announcement in issue #333: *"no longer being actively developed… issues are unlikely to be addressed and new updates should not be expected."* No release since 1.2.16 (2022-09-16).
2. **pylogix is actively maintained.** 13 PyPI releases in 2024–2026, last commit 2026-05-18. 712 stars / 200 forks / 75 watchers.
3. **API parity is high** for 5 of 7 methods (connection, tag list, program list, single read, discover). 2 methods require non-trivial rewrites: `get_plc_info` (different return shape) and `get_tag_info` (no direct equivalent — must walk `plc.UDTByName`).
4. **The UDT deal-breaker is mitigated.** pylogix does build a UDT cache (`plc.UDT` / `plc.UDTByName`) — it's just not exposed as a clean per-tag accessor. Our `_parse_structure_def` recursion needs a small rewrite, but the GUI's "drill into UDT" feature is salvageable.
5. **Migration cost is modest:** ~12–16 hours for code, ~16 hours for new tests, ~3–4 hours for the planned Discover feature, plus a half-day of bench validation against a real PLC. Roughly **3–4 person-days** total.
6. **Threading rules are identical** to pycomm3 (one instance per thread). No regression.
7. **Wire protocol is identical** (UDP broadcast 255.255.255.255:44818, CIP service 0x63), so behavior on the network is the same.

**The caveat:** pylogix's "no per-tag UDT accessor" gap is real and documented as an open issue (#125 since 2020-04-20). If the future PySide6 GUI grows a sophisticated UDT browser (showing External Access masks, descriptions, radix, dimensions, etc.), pylogix will not be able to provide those data points and we will hit a wall. pycomm3 has them. For the currently-planned GUI scope (tree view + read/write values + monitoring), pylogix is sufficient.

**Risk-adjusted recommendation:** Migrate. Build the UDT walker in pylogix today; if the UDT feature ever requires fields pylogix can't deliver, that is the trigger to either (a) contribute the accessor upstream (open PR on issue #125) or (b) vendor a thin pycomm3-only UDT-introspection helper inside our project (call `pycomm3.LogixDriver.get_tag_info` for the structure, pylogix for everything else). The status quo — staying on a frozen pycomm3 — is strictly worse because every PySide6 / Python 3.13+ / wheel-build CI issue we hit in 2027 and beyond will be unaddressed.

---

## Sources Cited

| Topic | URL |
|---|---|
| pylogix PyPI metadata | https://pypi.org/project/pylogix/ |
| pylogix 1.1.5 wheel | https://pypi.org/project/pylogix/1.1.5/ |
| pylogix repo | https://github.com/dmroeder/pylogix |
| pylogix repo API (pushed_at, stars, etc.) | https://api.github.com/repos/dmroeder/pylogix |
| pylogix source | `pylogix/eip.py`, `pylogix/lgx_comm.py`, `pylogix/lgx_response.py`, `pylogix/lgx_tag.py`, `pylogix/lgx_device.py`, `pylogix/__init__.py` (master branch) |
| pylogix documentation | https://github.com/dmroeder/pylogix/blob/master/docs/Documentation.md |
| pylogix Emulate guide | https://github.com/dmroeder/pylogix/blob/master/docs/Emulate.md |
| UDT open issue | https://github.com/dmroeder/pylogix/issues/125 |
| Subnet discover open issue | https://github.com/dmroeder/pylogix/issues/93 |
| VLAN discover open issue | https://github.com/dmroeder/pylogix/issues/111 |
| Connection maintenance open issue | https://github.com/dmroeder/pylogix/issues/188 |
| Multiple-PLC closed issue (with maintainer recommendation) | https://github.com/dmroeder/pylogix/issues/105 |
| pycomm3 PyPI metadata | https://pypi.org/project/pycomm3/ |
| pycomm3 repo | https://github.com/ottowayi/pycomm3 |
| pycomm3 "Project Status" announcement | https://github.com/ottowayi/pycomm3/issues/333 |
| pycomm3 source (for parity reference) | `pycomm3/logix_driver.py`, `pycomm3/cip_driver.py` (master branch) |
| Local target file | `C:\Users\adamssc\OneDrive - Continental Resources\Documents\Cursor\PLC Toolkit\ab_poller\plc_toolkit_consolidated.py` |