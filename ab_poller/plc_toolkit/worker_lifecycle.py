"""Shared helpers for stopping QThread workers without UI races."""

from __future__ import annotations

from typing import Iterable, Optional

from PySide6.QtCore import QThread


def disconnect_signal(signal) -> None:
    """Disconnect every slot from *signal* (ignore if already disconnected)."""
    try:
        signal.disconnect()
    except (RuntimeError, TypeError):
        pass


def disconnect_worker_signals(
    worker,
    names: Iterable[str] = (
        "started",
        "progress",
        "finished",
        "failed",
        "sample",
        "stopped",
        "chunk_loaded",
    ),
) -> None:
    """Disconnect all known worker signal objects from their slots."""
    signals = getattr(worker, "signals", None)
    if signals is None:
        return
    for name in names:
        sig = getattr(signals, name, None)
        if sig is not None:
            disconnect_signal(sig)


def wait_for_thread(
    thread: QThread,
    wait_ms: int = 8000,
) -> bool:
    """Block until *thread* exits or *wait_ms* elapses. Returns True if stopped."""
    if not thread.isRunning():
        return True
    if thread.wait(wait_ms):
        return True
    return not thread.isRunning()


def stop_qthread(
    thread: Optional[QThread],
    *,
    wait_ms: int = 8000,
    terminate_after_ms: Optional[int] = None,
) -> None:
    """Best-effort cooperative stop for a plain QThread worker."""
    if thread is None:
        return
    if hasattr(thread, "stop") and callable(thread.stop):
        thread.stop()
    elif hasattr(thread, "requestInterruption"):
        thread.requestInterruption()
    if wait_for_thread(thread, wait_ms):
        return
    if terminate_after_ms is not None and thread.isRunning():
        thread.terminate()
        thread.wait(terminate_after_ms)
