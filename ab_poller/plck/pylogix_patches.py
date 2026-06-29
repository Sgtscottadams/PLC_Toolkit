"""Local resilience shims for pylogix internals.

Why this exists
---------------
pylogix 1.1.5 aborts tag discovery on some controllers. In
``eip.PLC._get_udt`` it does::

    temp = self._get_template_attribute(u.DataTypeValue)
    block = temp[46:]

``_get_template_attribute`` (and ``_get_template``) return the raw socket
payload, which is ``None`` when the controller rejects or times out the
UDT *template* service. ``temp[46:]`` then raises
``'NoneType' object is not subscriptable`` and the whole ``GetTagList``
fails — even though the controller-scope and atomic tags came back fine.
This was observed on field CompactLogix/ControlLogix units that restrict
the template object service.

AGENTS.md mandates a single comms library (pylogix) and prefers a small
local helper over a second library, so we patch defensively at runtime
instead of vendoring a fork:

1. Coerce a ``None`` template payload to empty bytes. pylogix already has
   an "invalid template attribute" branch (it prints and skips that UDT),
   so the good UDTs still expand and atomic data types are still assigned.
2. Wrap ``_get_udt`` so any residual failure degrades to the flat tag
   list (discovery succeeds without UDT member expansion) rather than
   killing discovery entirely.

The shim is idempotent and safe to call at import time.
"""

from __future__ import annotations

# Original unbound methods, captured at install time. Kept at module
# scope so tests can exercise the wrappers deterministically.
_ORIGINALS: dict = {}


def install() -> None:
    """Apply the pylogix resilience shims once. Idempotent."""
    if _ORIGINALS:
        return
    from pylogix.eip import PLC

    _ORIGINALS["get_template_attribute"] = PLC._get_template_attribute
    _ORIGINALS["get_template"] = PLC._get_template
    _ORIGINALS["get_udt"] = PLC._get_udt

    def _safe_get_template_attribute(self, instance):
        data = _ORIGINALS["get_template_attribute"](self, instance)
        return data if data is not None else b""

    def _safe_get_template(self, instance, data_len):
        data = _ORIGINALS["get_template"](self, instance, data_len)
        return data if data is not None else b""

    def _safe_get_udt(self, tag_list):
        try:
            return _ORIGINALS["get_udt"](self, tag_list)
        except Exception:
            # Controller rejected/timed out the UDT template service.
            # Degrade gracefully: return the flat tag list so discovery
            # still yields usable (atomic / top-level) tags instead of
            # crashing with 'NoneType' object is not subscriptable.
            return tag_list

    PLC._get_template_attribute = _safe_get_template_attribute
    PLC._get_template = _safe_get_template
    PLC._get_udt = _safe_get_udt
