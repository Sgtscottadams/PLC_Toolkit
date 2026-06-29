"""Persistent application settings for PLC Toolkit v2."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


def install_dir() -> Path:
    """Directory containing the running app (exe folder when frozen)."""
    home = os.environ.get("PLC_TOOLKIT_HOME", "").strip()
    if home:
        return Path(home).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _has_portable_marker() -> bool:
    try:
        base = install_dir()
        return (base / "data" / "portable.marker").is_file() or (
            base / "portable.marker"
        ).is_file()
    except OSError:
        return False


def path_under_install(path: Path) -> bool:
    """True when *path* resolves inside the portable app folder."""
    try:
        base = install_dir().resolve()
        candidate = path.resolve()
    except (OSError, ValueError):
        return False
    if candidate == base:
        return True
    try:
        candidate.relative_to(base)
        return True
    except ValueError:
        return False


def _expand_path(text: str) -> Path | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return Path(os.path.expandvars(raw)).expanduser().resolve()
    except (OSError, ValueError):
        return None


def _effective_path_setting(stored: str) -> str:
    """Return a stored path only when it is valid for the current run mode."""
    if not (stored or "").strip():
        return ""
    resolved = _expand_path(stored)
    if resolved is None:
        return ""
    if portable_mode() and not path_under_install(resolved):
        return ""
    return stored.strip()


def portable_mode() -> bool:
    """True for PyInstaller builds or when PLC_TOOLKIT_PORTABLE is set."""
    flag = os.environ.get("PLC_TOOLKIT_PORTABLE", "").strip().lower()
    if flag in ("1", "true", "yes"):
        return True
    if getattr(sys, "frozen", False):
        return True
    return _has_portable_marker()


def app_data_dir() -> Path:
    if portable_mode():
        d = install_dir() / "data"
        d.mkdir(parents=True, exist_ok=True)
        return d
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    d = base / "PLCToolkit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_documents_dir() -> Path:
    """User Documents folder (follows OneDrive Known Folder Move on Windows)."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            csidl_personal = 0x0005
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(
                None, csidl_personal, None, 0, buf
            ) == 0:
                docs = Path(buf.value)
                if docs.is_dir():
                    return docs
        except Exception:
            pass
    docs = Path.home() / "Documents"
    return docs


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def ensure_portable_layout() -> None:
    """Create portable folders and a clean settings file before first use."""
    if not portable_mode():
        return
    base = install_dir()
    for name in ("data", "scans", "exports"):
        (base / name).mkdir(parents=True, exist_ok=True)
    # Keep the extracted root clean (folders + exe only): the marker lives
    # in data/. A legacy root-level marker is migrated, not duplicated.
    legacy_marker = base / "portable.marker"
    marker = base / "data" / "portable.marker"
    if legacy_marker.is_file() and not marker.is_file():
        try:
            legacy_marker.replace(marker)
        except OSError:
            legacy_marker.unlink(missing_ok=True)
    elif legacy_marker.is_file():
        legacy_marker.unlink(missing_ok=True)
    if not marker.is_file():
        marker.write_text(
            "PLC Toolkit portable deploy\n"
            "Double-click PLC_Toolkit.exe in the parent folder to run.\n",
            encoding="utf-8",
        )
    path = settings_path()
    if not path.is_file():
        AppSettings().save(path)
        return
    settings = AppSettings.load(path)
    settings.save(path)


@dataclass
class AppSettings:
    """Wireframe-core settings (Connection, Polling, Storage, Export)."""

    # Connection
    connection_timeout_s: float = 5.0
    connect_retries: int = 3
    retry_delay_ms: int = 500
    auto_reconnect: bool = True
    default_port: int = 44818
    verify_ip_before_cip: bool = True
    default_discover_network: str = ""
    default_discover_cidr: str = "/24"

    # Polling & display
    default_poll_rate_s: float = 5.0
    bool_display: str = "0 / 1"  # "FALSE / TRUE" | "Off / On"
    trend_window_samples: int = 60

    # Storage
    db_path: str = ""
    scans_dir: str = ""
    retention_days: int = 90
    auto_prune_scans: bool = True

    # Export
    export_dir: str = ""
    filename_template: str = "{ip}_{nickname}_{YYYY-MM-DD}_{HHmm}"

    # Theme
    theme: str = "dark"  # "dark" | "light"

    def resolved_db_path(self) -> Path:
        stored = _effective_path_setting(self.db_path)
        if stored:
            return Path(os.path.expandvars(stored)).expanduser()
        return app_data_dir() / "plc_data.db"

    def resolved_scans_dir(self) -> Path:
        stored = _effective_path_setting(self.scans_dir)
        if stored:
            return Path(os.path.expandvars(stored)).expanduser()
        if portable_mode():
            d = install_dir() / "scans"
            d.mkdir(parents=True, exist_ok=True)
            return d
        return app_data_dir() / "plc_scans"

    def resolved_export_dir(self) -> Path:
        stored = _effective_path_setting(self.export_dir)
        if stored:
            return Path(os.path.expandvars(stored)).expanduser()
        if portable_mode():
            d = install_dir() / "exports"
            d.mkdir(parents=True, exist_ok=True)
            return d
        return default_documents_dir() / "PLCToolkit" / "exports"

    def sanitize_portable_paths(self) -> bool:
        """Drop storage paths outside the app folder when running portable."""
        if not portable_mode():
            return False
        cleaned = AppSettings(
            **{
                **asdict(self),
                "db_path": _effective_path_setting(self.db_path),
                "scans_dir": _effective_path_setting(self.scans_dir),
                "export_dir": _effective_path_setting(self.export_dir),
            }
        )
        changed = (
            cleaned.db_path != self.db_path
            or cleaned.scans_dir != self.scans_dir
            or cleaned.export_dir != self.export_dir
        )
        if changed:
            self.db_path = cleaned.db_path
            self.scans_dir = cleaned.scans_dir
            self.export_dir = cleaned.export_dir
        return changed

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "AppSettings":
        p = path or settings_path()
        if not p.is_file():
            return cls()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            allowed = {f.name for f in cls.__dataclass_fields__.values()}
            filtered = {k: v for k, v in raw.items() if k in allowed}
            settings = cls(**filtered)
        except (json.JSONDecodeError, TypeError, ValueError):
            return cls()
        if settings.sanitize_portable_paths():
            settings.save(p)
        return settings

    def save(self, path: Optional[Path] = None) -> None:
        p = path or settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
