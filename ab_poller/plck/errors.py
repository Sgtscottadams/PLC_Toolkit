"""plck exception hierarchy.

One base + four concrete. Catch PlcError for "any plck failure". The
subclasses are for cases where the caller wants to handle a specific
failure mode (e.g. a timeout during a subnet scan should not abort the
whole scan; it should be recorded per-host).
"""

from __future__ import annotations


class PlcError(Exception):
    """Base class for all plck exceptions."""


class PlcTimeout(PlcError):
    """A read or connect call did not complete in time.

    This is the most common transient error on a SCADA network: the PLC
    is on a slow link, the broadcast storm from another tool is in
    progress, etc. Callers should typically retry with backoff.
    """


class PlcAuthError(PlcError):
    """Authentication / authorization failure.

    The PLC responded but rejected the request (e.g. the .C configuration
    tag is locked when the controller is in Run mode). Not retryable
    without changing the controller state.
    """


class PlcUnsupported(PlcError):
    """The requested operation is not supported by the connected PLC.

    Examples: requesting tag info on a non-UDT tag, asking for CIP path
    routing on a MicroLogix that doesn't support backplane routes.
    """


class PlcCommError(PlcError):
    """Generic communication failure (socket closed, malformed response,
    unexpected protocol error). Retriable. Distinguished from PlcTimeout
    because the failure was immediate, not a wait.
    """
