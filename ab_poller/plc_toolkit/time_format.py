"""Display formatting for scan timestamps (Central Time for field ops)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def _central_tz():
    try:
        return ZoneInfo("America/Chicago")
    except Exception:
        # Windows without tzdata: fixed CST (no DST). Install tzdata for accuracy.
        return timezone(timedelta(hours=-6))


CENTRAL = _central_tz()


def format_scan_timestamp(iso_ts: str) -> str:
    """Format an ISO-8601 UTC scan timestamp as Central Time.

    Output: ``YYYY-MM-DD - HH:MM`` (24-hour clock).
    """
    raw = (iso_ts or "").strip()
    if not raw:
        return "—"
    try:
        if raw.endswith("Z"):
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        elif "+" in raw or raw.count("-") > 2:
            dt = datetime.fromisoformat(raw)
        else:
            dt = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(CENTRAL)
        return local.strftime("%Y-%m-%d - %H:%M")
    except (ValueError, TypeError):
        return raw[:16] if len(raw) >= 16 else raw


def format_scan_timestamp_long(iso_ts: str) -> str:
    """Longer label for dialogs: includes Central timezone name."""
    base = format_scan_timestamp(iso_ts)
    if base == "—":
        return base
    return f"{base} Central"


def monitor_sample_timestamp() -> str:
    """Central Time label for a live monitor sample (includes date + seconds)."""
    return datetime.now(CENTRAL).strftime("%Y-%m-%d - %H:%M:%S")


def parse_monitor_sample_timestamp(ts: str) -> datetime | None:
    """Parse a monitor sample label back to Central ``datetime``."""
    raw = (ts or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d - %H:%M:%S").replace(tzinfo=CENTRAL)
    except ValueError:
        return None


def format_monitor_trend_span(first_ts: str | None) -> str:
    """Monitor Trend column header: first sample time through now (Central).

    Same calendar day: ``09:15 - 14:32``. If the first sample is from a prior
    day, the start includes the date: ``2026-06-23 22:00 - 06:15``.
    """
    if not first_ts:
        return "Trend"
    first = parse_monitor_sample_timestamp(first_ts)
    if first is None:
        return "Trend"
    now = datetime.now(CENTRAL)
    if first.date() < now.date():
        start = first.strftime("%Y-%m-%d %H:%M")
    else:
        start = first.strftime("%H:%M")
    end = now.strftime("%H:%M")
    return f"{start} - {end}"
