"""plck.comms — Thread-safe pylogix wrapper.

pylogix is NOT thread-safe across shared instances. The official guidance
is one PLC() instance per thread. PLCClient enforces this rule and
provides:

    1. Lifecycle management: connect, get_device_info, close.
    2. Thread-safety: every method asserts the instance is being called
       from the thread that constructed it.
    3. Error normalization: pylogix returns Response objects with a
       Status string ("Success" or a CIP error). PLCClient surfaces
       failures as plck exceptions (PlcTimeout, PlcAuthError, etc.) and
       success as plain Python values.
    4. Cancellation: every long-running call accepts an optional
       `cancel: threading.Event` so a Qt thread can interrupt cleanly.

The wrapper does NOT:
    * Cache tag lists (that's discovery's job, and we don't want stale
      data when the operator hits Re-discover).
    * Implement auto-reconnect (that's the GUI's responsibility — the
      GUI owns the lifecycle and the user-visible status).
    * Aggregate multiple PLCs (each PLCClient is one connection; the
      GUI creates one per workspace tab).
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import pylogix
from pylogix import PLC

import plck.pylogix_patches as _pylogix_patches
from plck.device_filter import filter_tag_readable_devices

# Make pylogix's UDT template discovery resilient to controllers that
# reject/time out the template service (otherwise GetTagList crashes with
# 'NoneType' object is not subscriptable). Applied once at import.
_pylogix_patches.install()
from plck.errors import (
    PlcError, PlcTimeout, PlcAuthError, PlcUnsupported, PlcCommError,
)
from plck.models import PlcConnection, ReadResult, ReadQuality


# pylogix maps CIP errors to specific status strings. A subset of the
# common ones is mapped to typed exceptions. Anything not on the list
# becomes a generic PlcCommError.
_PRIVILEGE_VIOLATION = "Privilege violation"
_PATH_SEGMENT = "Path segment error"
_INVALID_PARAMETER = "Invalid parameter"
_UNSUPPORTED = "Unsupported service"
_TIMEOUT_PYL = "SocketTimeout"
_COMMUNICATION = "Connection lost"
_GENERAL_COMMUNICATION = "General communication error"


class PLCClient:
    """Thread-pinned wrapper around pylogix.PLC.

    Construct one PLCClient per worker thread. Do not call methods from
    a different thread — the assertion in _check_owner will raise.
    """

    def __init__(self, plc: PlcConnection, timeout_s: float = 5.0) -> None:
        self.plc = plc
        self.timeout_s = timeout_s
        self._owner = threading.get_ident()
        # Use Micro800 only for Micro800 series; for ControlLogix/CompactLogix
        # the default (Micro800=False) is correct. The library auto-detects
        # the slot from the controller type, so we pass slot as the wire
        # parameter when slot>=0, otherwise the controller's "current" slot.
        # pylogix uses slot=0 by default which is the most common case.
        self._client = PLC(
            ip_address=plc.ip,
            slot=plc.slot,
            timeout=timeout_s,
            Micro800=False,
            port=plc.port,
        )

    # -- Thread safety ---------------------------------------------------

    def _check_owner(self) -> None:
        if threading.get_ident() != self._owner:
            raise PlcError(
                "PLCClient was constructed on one thread and is being "
                "called from another. pylogix is not thread-safe; create "
                "one PLCClient per worker thread."
            )

    # -- Lifecycle -------------------------------------------------------

    def get_device_info(self) -> PlcConnection:
        """Query the PLC and populate the PlcConnection's discovery fields.

        Returns the same PlcConnection (mutated in place AND returned for
        convenience). Updates vendor / product_name / revision / serial_number.
        """
        self._check_owner()
        r = self._client.GetDeviceProperties()
        self._raise_for_status(r.Status)
        v = r.Value
        if v is not None:
            self.plc.vendor = v.Vendor
            self.plc.product_name = v.ProductName
            self.plc.revision = v.Revision
            self.plc.serial_number = v.SerialNumber
        return self.plc

    def close(self) -> None:
        """Best-effort close. pylogix auto-closes per-call; this is for
        symmetry with the open/close idiom and to make the GUI's
        Disconnect button feel honest.
        """
        self._check_owner()
        # pylogix does not expose a public Close() — connections are
        # request-scoped. We do nothing here.
        return None

    # -- Reads -----------------------------------------------------------

    def read(self, tag: str) -> ReadResult:
        """Single-tag read. Errors come back as ReadResult with
        quality=BAD and a populated error string — they do NOT raise
        unless the failure is at the protocol level (timeout, socket
        error), in which case we raise a typed exception.
        """
        self._check_owner()
        t0 = time.monotonic()
        try:
            r = self._client.Read(tag)
        except Exception as e:  # pylogix raises on socket failure
            self._raise_for_pylogix_exception(e)
        elapsed_ms = (time.monotonic() - t0) * 1000.0

        if r.Status == "Success":
            return ReadResult(
                tag_name=tag,
                value=r.Value,
                quality=ReadQuality.GOOD,
                elapsed_ms=elapsed_ms,
            )
        # CIP error — return as BAD quality with the status string.
        return ReadResult(
            tag_name=tag,
            value=None,
            quality=ReadQuality.BAD,
            error=str(r.Status),
            elapsed_ms=elapsed_ms,
        )

    def read_many(self, tags: list[str]) -> list[ReadResult]:
        """Multi-tag read. pylogix returns a list of Responses for a list
        input; we map each to a ReadResult.
        """
        self._check_owner()
        if not tags:
            return []
        t0 = time.monotonic()
        try:
            responses = self._client.Read(tags)
        except Exception as e:
            self._raise_for_pylogix_exception(e)
        elapsed_ms = (time.monotonic() - t0) * 1000.0

        # pylogix returns a list[Response] when given a list. Preserve
        # order matching `tags` so the caller can correlate.
        if not isinstance(responses, list):
            responses = [responses]
        out: list[ReadResult] = []
        per_tag_ms = elapsed_ms / max(1, len(tags))
        for tag, r in zip(tags, responses):
            if r.Status == "Success":
                out.append(ReadResult(
                    tag_name=tag, value=r.Value,
                    quality=ReadQuality.GOOD,
                    elapsed_ms=per_tag_ms,
                ))
            else:
                out.append(ReadResult(
                    tag_name=tag, value=None,
                    quality=ReadQuality.BAD,
                    error=str(r.Status),
                    elapsed_ms=per_tag_ms,
                ))
        return out

    # -- Discovery helpers (low-level) ---------------------------------

    def get_tag_list(self, all_tags: bool = True) -> list:
        """Low-level call to pylogix's GetTagList. Returns the raw
        pylogix.Tag list. The high-level tree builder lives in
        plck.discovery.

        all_tags=True walks UDTs (slower) and populates the pylogix
        UDT cache. all_tags=False returns only top-level tag names.
        """
        self._check_owner()
        try:
            r = self._client.GetTagList(allTags=all_tags)
        except Exception as e:
            self._raise_for_pylogix_exception(e)
        if r.Status != "Success":
            self._raise_for_status(r.Status)
        return list(r.Value or [])

    def get_programs_list(self) -> list[str]:
        """List program names. pylogix auto-strips the 'Program:' prefix."""
        self._check_owner()
        try:
            r = self._client.GetProgramsList()
        except Exception as e:
            self._raise_for_pylogix_exception(e)
        if r.Status != "Success":
            self._raise_for_status(r.Status)
        return list(r.Value or [])

    def get_program_tag_list(self, program: str) -> list:
        """List tags in a specific program. `program` may be 'MainProgram'
        (pylogix adds the 'Program:' prefix) or 'Program:MainProgram'.
        """
        self._check_owner()
        # pylogix expects 'Program:Name'
        if not program.startswith("Program:"):
            program = f"Program:{program}"
        try:
            r = self._client.GetProgramTagList(program)
        except Exception as e:
            self._raise_for_pylogix_exception(e)
        if r.Status != "Success":
            self._raise_for_status(r.Status)
        return list(r.Value or [])

    # -- Subnet discovery ------------------------------------------------

    def discover(
        self,
        subnet_cidr=None,
        progress_cb=None,
        probe_timeout_s: float = 2.0,
        max_workers: int = 20,
    ):
        """Run a one-shot subnet discovery. Returns a list of dicts:
            {ip, vendor, product_name, revision, serial_number, state}

        If *subnet_cidr* is given, tries UDP ListIdentity broadcast filtered
        to the subnet, then a concurrent direct TCP scan of remaining hosts
        (reliable when broadcast is blocked).  Otherwise uses pylogix's
        unfiltered Discover() broadcast.

        *progress_cb* is called as progress_cb(msg) during direct scans.
        """
        self._check_owner()
        if subnet_cidr:
            return self._discover_direct(
                subnet_cidr,
                progress_cb=progress_cb,
                probe_timeout_s=probe_timeout_s,
                max_workers=max_workers,
            )
        try:
            r = self._client.Discover()
        except Exception as e:
            self._raise_for_pylogix_exception(e)
        if r.Status != "Success":
            self._raise_for_status(r.Status)
        out = []
        for d in (r.Value or []):
            out.append({
                "ip": d.IPAddress,
                "vendor": d.Vendor,
                "product_name": d.ProductName,
                "revision": d.Revision,
                "serial_number": d.SerialNumber,
                "state": d.State,
            })
        return filter_tag_readable_devices(out)

    def _discover_udp_filtered(self, subnet_cidr: str) -> list[dict]:
        """Broadcast ListIdentity and keep devices inside *subnet_cidr*."""
        network = _ip_to_network(subnet_cidr)
        try:
            r = self._client.Discover()
        except Exception as e:
            self._raise_for_pylogix_exception(e)
        if r.Status != "Success":
            return []
        out: list[dict] = []
        seen: set[str] = set()
        for d in (r.Value or []):
            ip = d.IPAddress
            if ip in seen or not _ip_in_network(ip, network):
                continue
            seen.add(ip)
            out.append({
                "ip": ip,
                "vendor": d.Vendor,
                "product_name": d.ProductName,
                "revision": d.Revision,
                "serial_number": d.SerialNumber,
                "state": d.State,
            })
        return out

    def _discover_direct(
        self,
        subnet_cidr,
        progress_cb=None,
        probe_timeout_s: float = 2.0,
        max_workers: int = 20,
    ):
        """Subnet discovery: UDP broadcast (filtered) + concurrent TCP probes.

        UDP ListIdentity is tried first because it is fast when the network
        allows broadcast.  Remaining hosts are probed concurrently via TCP
        port 44818 and GetDeviceProperties() for networks where broadcast
        is blocked or filtered.

        If *progress_cb* is callable, it's invoked as progress_cb(msg) so
        the UI can update the status line and progress bar.
        """
        import ipaddress

        network_int, prefix = _ip_to_network(subnet_cidr)
        net = ipaddress.IPv4Network((network_int, prefix), strict=False)
        hosts = [str(a) for a in net.hosts()]
        total = len(hosts)

        if progress_cb:
            progress_cb(
                f"Trying UDP ListIdentity broadcast for {subnet_cidr}…"
            )

        found: dict[str, dict] = {}
        for device in self._discover_udp_filtered(subnet_cidr):
            found[device["ip"]] = device

        if progress_cb and found:
            progress_cb(
                f"UDP broadcast found {len(found)} device(s). "
                f"Scanning remaining hosts…"
            )

        remaining = [ip for ip in hosts if ip not in found]
        completed = total - len(remaining)

        if remaining:
            if progress_cb:
                progress_cb(
                    f"Scanning {subnet_cidr}: starting direct TCP probes "
                    f"({completed}/{total})"
                )
            port = self.plc.port
            slot = self.plc.slot
            timeout_s = self.timeout_s
            workers = max(1, min(max_workers, len(remaining)))

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(
                        _probe_plc_host,
                        ip,
                        port,
                        slot,
                        timeout_s,
                        probe_timeout_s,
                    ): ip
                    for ip in remaining
                }
                for fut in as_completed(futures):
                    completed += 1
                    ip = futures[fut]
                    if progress_cb:
                        progress_cb(
                            f"Scanning {subnet_cidr}: {ip} ({completed}/{total})"
                        )
                    result = fut.result()
                    if result is not None and result["ip"] not in found:
                        found[result["ip"]] = result

        if progress_cb:
            progress_cb(
                f"Scan complete: {len(found)} device(s) on {subnet_cidr}."
            )
        return filter_tag_readable_devices(list(found.values()))

    # -- Internal helpers -----------------------------------------------

    def _raise_for_status(self, status: str) -> None:
        if status == "Success":
            return
        s = str(status)
        if not s.strip():
            raise PlcCommError(
                "PLC returned an empty status during EtherNet/IP discovery. "
                "Connection test succeeded, but the controller did not return "
                "a usable status for the requested tag-list/program-list call."
            )
        if s == _PRIVILEGE_VIOLATION or s == _PATH_SEGMENT or s == _INVALID_PARAMETER:
            raise PlcAuthError(s)
        if s == _UNSUPPORTED:
            raise PlcUnsupported(s)
        # Everything else: generic comm error.
        raise PlcCommError(s)

    def _raise_for_pylogix_exception(self, e: Exception) -> None:
        """Translate a pylogix-raised exception (vs a status-string) into
        a typed plck exception.
        """
        name = type(e).__name__
        msg = str(e)
        if "SocketTimeout" in name or "timeout" in msg.lower():
            raise PlcTimeout(msg) from e
        if "Connection" in name or "Connection" in msg:
            raise PlcCommError(msg) from e
        raise PlcError(msg) from e


# -- Subnet filter helpers ---------------------------------------------------


def _ip_to_network(cidr):
    """Parse a user-supplied subnet spec into a (network_int, prefix_len) tuple.

    Accepts:
        '172.17.117.0/24'  — CIDR notation
        '172.17.117.255'   — broadcast address (infer /24)
        '172.17.117.0'     — network address (infer /24)
        '172.17.117.140'   — host IP (infer /24)
    """
    import ipaddress
    cidr = cidr.strip()

    # If the string contains a '/' it's an explicit CIDR — use it directly.
    if "/" in cidr:
        try:
            net = ipaddress.IPv4Network(cidr, strict=False)
            return (int(net.network_address), net.prefixlen)
        except (ValueError, ipaddress.AddressValueError):
            raise ValueError(f"Invalid CIDR: {cidr!r}")

    # Bare IP (host or broadcast) — infer /24.
    try:
        addr = ipaddress.IPv4Address(cidr)
        net = ipaddress.IPv4Network(f"{addr}/24", strict=False)
        return (int(net.network_address), net.prefixlen)
    except (ValueError, ipaddress.AddressValueError):
        raise ValueError(f"Invalid subnet spec: {cidr!r}")


def _ip_in_network(ip_str, network):
    """Return True if *ip_str* is inside *network* (network_int, prefix_len)."""
    import ipaddress
    try:
        addr = ipaddress.IPv4Address(ip_str)
    except (ValueError, ipaddress.AddressValueError):
        return False
    net_int, prefix = network
    host_int = int(addr)
    mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    return (host_int & mask) == net_int


def _port_open(ip, port, timeout_s=0.5):
    """Return True if *ip*:*port* accepts a TCP connection within *timeout_s*."""
    import socket as _socket
    s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    s.settimeout(timeout_s)
    try:
        s.connect((ip, port))
        s.close()
        return True
    except OSError:
        return False


def _probe_plc_host(
    ip: str,
    port: int,
    slot: int,
    timeout_s: float,
    probe_timeout_s: float,
) -> Optional[dict]:
    """Try one host for an EtherNet/IP device. Thread-safe (no PLCClient)."""
    if not _port_open(ip, port, timeout_s=probe_timeout_s):
        return None
    try:
        probe = PLC(
            ip_address=ip,
            slot=slot,
            timeout=int(timeout_s),
            Micro800=False,
            port=port,
        )
        r = probe.GetDeviceProperties()
        if r.Status == "Success" and r.Value is not None:
            v = r.Value
            return {
                "ip": ip,
                "vendor": v.Vendor,
                "product_name": v.ProductName,
                "revision": v.Revision,
                "serial_number": v.SerialNumber,
                "state": 0,
            }
    except Exception:
        return None
    return None
