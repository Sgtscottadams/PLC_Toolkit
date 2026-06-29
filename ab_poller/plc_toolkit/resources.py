"""Resolve bundled asset files for dev and PyInstaller builds."""

from __future__ import annotations

import sys
from pathlib import Path

from plc_toolkit.settings_store import install_dir


def asset_path(filename: str) -> Path | None:
    """Return the first existing path for *filename* under ``assets/``."""
    pkg = Path(__file__).resolve().parent
    candidates: list[Path] = []

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "plc_toolkit" / "assets" / filename)

    candidates.extend(
        [
            pkg / "assets" / filename,
            install_dir() / "assets" / filename,
            pkg.parent.parent.parent / "mockups" / "assets" / filename,
        ]
    )

    for path in candidates:
        if path.is_file():
            return path
    return None
