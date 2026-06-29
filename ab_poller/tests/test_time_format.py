from __future__ import annotations

from plc_toolkit.time_format import monitor_sample_timestamp


def test_monitor_sample_timestamp_includes_date_and_seconds():
    ts = monitor_sample_timestamp()
    assert " - " in ts
    parts = ts.split(" - ")
    assert len(parts) == 2
    date_part, time_part = parts
    assert len(date_part.split("-")) == 3
    assert len(time_part.split(":")) == 3


def test_format_monitor_trend_span_same_day():
    from datetime import datetime

    from plc_toolkit.time_format import CENTRAL, format_monitor_trend_span

    today = datetime.now(CENTRAL).strftime("%Y-%m-%d - %H:%M:%S")
    label = format_monitor_trend_span(today)
    start, end = label.split(" - ")
    assert len(start) == 5 and start[2] == ":"
    assert len(end) == 5 and end[2] == ":"
    assert start.count("-") == 0


def test_format_monitor_trend_span_prior_day():
    from plc_toolkit.time_format import format_monitor_trend_span

    label = format_monitor_trend_span("2020-01-01 - 22:15:00")
    assert label.startswith("2020-01-01 22:15")
    assert " - " in label
