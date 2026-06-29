# Research Summary — pycomm3 Subnet-Discovery API

**Status:** Research complete. Sources: upstream pycomm3 source tarball (master branch, version 1.2.16), live PyPI JSON API, in-repo RST documentation files, runtime `hasattr` checks on the installed package.

---

## What I did

1. Pulled live PyPI metadata for `pycomm3` → confirmed latest version and upload time.
2. Downloaded the full upstream source tarball (`codeload.github.com/ottowayi/pycomm3/tar.gz/refs/heads/master`) into `/tmp/pycomm3-master/` and read:
   - `pycomm3/cip_driver.py` (the discovery implementation)
   - `pycomm3/cip/services.py` (encapsulation command codes)
   - `pycomm3/packets/ethernetip.py` (ListIdentity packet classes)
   - `pycomm3/slc_driver.py` (legacy AB driver — confirmed no port 55555)
   - `pycomm3/__init__.py` (verified there is no top-level `discover` export)
   - `examples/lgx_gui_test.py` (the threading/GUI pattern)
   - `docs/usage/cipdriver.rst` (the official docs page source)
   - `README.rst`, `docs/getting_started.rst`, `docs/releases.rst`
3. Imported `pycomm3` at runtime to verify classmethod inheritance and signatures (`hasattr(pycomm3, "discover") == False`; `CIPDriver`, `LogixDriver`, `SLCDriver` all expose `discover`).
4. Grepped the entire package for legacy ports (`2222`, `55555`, `CSPv4`, `slc-ethernet`) — zero matches.

---

## Findings — answering each of the 6 questions

### 1. Latest PyPI version
- **Version:** **1.2.16**
- **Uploaded:** **2025-12-22T17:33:05 UTC** (verified via PyPI JSON API)
- **Verified on:** 2026-06-16
- Previous was 1.2.14 (2023-08-27). The README now opens with: *"⚠️ NOTE: pycomm3 is no longer actively developed"*. Source: `pycomm3/_version.py`.

### 2. Top-level `discover()` vs classmethod
**There is no top-level `discover()` function.** `discover` is a `@classmethod` on `CIPDriver` and is inherited by `LogixDriver` and `SLCDriver`. Exact signatures from `pycomm3/cip_driver.py`:

```python
@classmethod
def list_identity(cls, path) -> Optional[Dict[str, Any]]: ...

@classmethod
def discover(cls, broadcast_address="255.255.255.255") -> List[Dict[str, Any]]:
    """Discovers available devices on the current network(s).
    Returns a list of the discovered devices Identity Object (as dict)."""
```

Runtime check: `hasattr(pycomm3, "discover") == False`; `hasattr(CIPDriver, "discover") == True` (and inherited by Logix/SLC).

### 3. ListIdentity probing — protocol details
- **Transport:** UDP broadcast (`socket.AF_INET`, `socket.SOCK_DGRAM`, `SO_BROADCAST=1`), 1-second timeout, bound to each local IPv4 from `socket.getaddrinfo()`.
- **Port:** **44818** (hardcoded at `cip_driver.py:247`: `sock.sendto(message, (broadcast_address, 44818))`). Not configurable.
- **Encapsulation command code:** **`0x0063`** ("ListIdentity") — this is an EtherNet/IP *encapsulation* command, not a CIP service. Defined in `pycomm3/cip/services.py`:
  ```python
  class EncapsulationCommands(EnumMap):
      list_identity = b"\x63\x00"
  ```
- **Packet class:** `ListIdentityRequestPacket` (`pycomm3/packets/ethernetip.py:246`) → `ListIdentityResponsePacket` decodes into a `ListIdentityObject` dict with fields: `encap_protocol_version, ip_address, vendor, product_type, product_code, revision, status, serial, product_name, state`.
- **TCP unicast variant:** `CIPDriver.list_identity(path)` opens a TCP connection on the same port 44818 and sends the same `0x0063` command.

### 4. Legacy AB ports — 2222 (CSPv4) and 55555 (slc-ethernet)
**pycomm3 has NO helpers for either port.** Full package grep yields zero hits for `2222`, `55555`, `CSPv4`, or `slc-ethernet`.
- `SLCDriver` (the legacy driver) still uses **EtherNet/IP on port 44818** — CIP encapsulation with PCCC inside `SendUnitData`. It inherits `discover()` from `CIPDriver` and so does the same UDP/44818 broadcast. It does **not** probe 55555.
- The README explicitly calls `SLCDriver` legacy/limited-development.
- To support CSPv4 (port 2222) or slc-ethernet DF1-over-TCP (port 55555), you would need to write raw socket code yourself or use a separate library (original `pycomm`, `pylogix`, or hand-rolled DF1).

### 5. Official example / docs page for subnet discovery
Yes — primary URL:
- **https://docs.pycomm3.dev/en/latest/usage/cipdriver.html** — section "Discovery and Identification" (RST source: `docs/usage/cipdriver.rst`, lines 11–48). Contains the canonical `CIPDriver.discover()` example with sample output.
- https://docs.pycomm3.dev/en/latest/ — docs index.
- https://docs.pycomm3.dev/en/latest/api_reference/cip_driver.html — auto-generated API reference for `CIPDriver.discover` / `list_identity`.
- **In-repo working example:** `examples/lgx_gui_test.py` — full Tkinter GUI with a "Discover Devices" button wired to a `threading.Thread` calling `LogixDriver(path).discover()` at line 419. Closest existing reference for discovery-driven UI.
- The `broadcast_address` parameter was added in **v1.2.13** (changelog: `docs/releases.rst` line 15, PR #292).

Note: the live `docs.pycomm3.dev` host was not reachable from this environment during research; conclusions are from the in-repo RST sources (which the site renders verbatim).

### 6. Non-blocking discovery in a PySide6 GUI
There is no PySide6 documentation upstream, but `examples/lgx_gui_test.py` (lines 60–88, 374–424) shows the working pattern. Key points for adapting to `QThread`:

1. `discover()` and `list_identity()` are **classmethods that open/close their own sockets** internally — safe to call from a worker thread, no shared mutable state.
2. Each broadcast opens a fresh socket with `sock.settimeout(1)` — a hung subnet cannot wedge the GUI.
3. Upstream uses `threading.Thread(...).setDaemon(True)` — maps directly to a PySide6 `QThread` subclass with `run()` calling `LogixDriver.discover()` or `CIPDriver.discover()` and emitting results via `pyqtSignal`.
4. **`broadcast_address` parameter** (default `"255.255.255.255"`, v1.2.13+) — useful for confining the scan to a specific subnet (`"192.168.1.255"`).
5. **Logging is global.** pycomm3 uses Python's `logging` module; configure once at startup and the worker thread's logs will flow to your GUI handler. No other module-level globals to worry about.
6. **Don't share a `CIPDriver`/`LogixDriver` instance across threads** — each instance owns one TCP socket. Use the classmethod, or a fresh instance per worker.
7. **Don't use a default `LogixDriver(path)` for discovery** — `init_tags=True` (default) uploads the entire tag list, which can take 10–15 s on a large program. The example uses `LogixDriver(path, init_tags=False, init_program_tags=False)` for discovery (line 411). For pure discovery, prefer **`CIPDriver.discover()`** (no tag upload).
