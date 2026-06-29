"""Settings persistence tests."""

from __future__ import annotations

import json
from pathlib import Path

from plc_toolkit.settings_store import AppSettings, app_data_dir, portable_mode


def test_default_filename_template():
    s = AppSettings()
    assert s.filename_template == "{ip}_{nickname}_{YYYY-MM-DD}_{HHmm}"


def test_default_paths_under_app_data(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "plc_toolkit.settings_store.default_documents_dir",
        lambda: tmp_path / "Documents",
    )
    monkeypatch.setattr("plc_toolkit.settings_store.portable_mode", lambda: False)
    s = AppSettings()
    assert s.resolved_db_path().name == "plc_data.db"
    assert s.resolved_scans_dir().name == "plc_scans"
    assert s.resolved_export_dir() == tmp_path / "Documents" / "PLCToolkit" / "exports"
    assert app_data_dir().name == "PLCToolkit"


def test_portable_default_paths(monkeypatch, tmp_path):
    monkeypatch.setattr("plc_toolkit.settings_store.portable_mode", lambda: True)
    monkeypatch.setattr(
        "plc_toolkit.settings_store.install_dir", lambda: tmp_path / "Toolkit"
    )
    monkeypatch.setattr(
        "plc_toolkit.settings_store.app_data_dir",
        lambda: tmp_path / "Toolkit" / "data",
    )
    s = AppSettings()
    assert s.resolved_export_dir() == tmp_path / "Toolkit" / "exports"
    assert s.resolved_scans_dir() == tmp_path / "Toolkit" / "scans"
    assert s.resolved_db_path() == tmp_path / "Toolkit" / "data" / "plc_data.db"


def test_portable_ignores_paths_outside_install_dir(monkeypatch, tmp_path):
    toolkit = tmp_path / "Toolkit"
    toolkit.mkdir()
    monkeypatch.setattr("plc_toolkit.settings_store.portable_mode", lambda: True)
    monkeypatch.setattr("plc_toolkit.settings_store.install_dir", lambda: toolkit)
    monkeypatch.setattr(
        "plc_toolkit.settings_store.app_data_dir", lambda: toolkit / "data"
    )
    s = AppSettings(
        db_path=r"C:\Users\me\AppData\Roaming\PLCToolkit\plc_data.db",
        scans_dir=r"C:\Users\me\AppData\Roaming\PLCToolkit\plc_scans",
        export_dir=r"C:\Users\me\Documents\PLCToolkit\exports",
    )
    assert s.resolved_db_path() == toolkit / "data" / "plc_data.db"
    assert s.resolved_scans_dir() == toolkit / "scans"
    assert s.resolved_export_dir() == toolkit / "exports"


def test_portable_mode_from_env(monkeypatch):
    monkeypatch.setenv("PLC_TOOLKIT_PORTABLE", "1")
    monkeypatch.setattr("plc_toolkit.settings_store._has_portable_marker", lambda: False)
    assert portable_mode() is True


def test_load_rewrites_foreign_portable_paths(monkeypatch, tmp_path):
    toolkit = tmp_path / "ShareApp"
    toolkit.mkdir()
    data = toolkit / "data"
    data.mkdir()
    settings_file = data / "settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "db_path": r"C:\Users\me\AppData\Roaming\PLCToolkit\plc_data.db",
                "export_dir": r"C:\Users\me\Documents\PLCToolkit\exports",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("plc_toolkit.settings_store.portable_mode", lambda: True)
    monkeypatch.setattr("plc_toolkit.settings_store.install_dir", lambda: toolkit)
    monkeypatch.setattr("plc_toolkit.settings_store.app_data_dir", lambda: data)
    monkeypatch.setattr(
        "plc_toolkit.settings_store.settings_path", lambda: settings_file
    )

    loaded = AppSettings.load()
    assert loaded.db_path == ""
    assert loaded.export_dir == ""
    assert loaded.resolved_db_path() == data / "plc_data.db"
    saved = json.loads(settings_file.read_text(encoding="utf-8"))
    assert saved.get("db_path") == ""
    assert saved.get("export_dir") == ""


def test_ensure_portable_layout_creates_folders(monkeypatch, tmp_path):
    toolkit = tmp_path / "Deploy"
    toolkit.mkdir()
    monkeypatch.setattr("plc_toolkit.settings_store.portable_mode", lambda: True)
    monkeypatch.setattr("plc_toolkit.settings_store.install_dir", lambda: toolkit)
    monkeypatch.setattr(
        "plc_toolkit.settings_store.settings_path",
        lambda: toolkit / "data" / "settings.json",
    )

    from plc_toolkit.settings_store import ensure_portable_layout

    ensure_portable_layout()
    assert (toolkit / "data" / "settings.json").is_file()
    assert (toolkit / "scans").is_dir()
    assert (toolkit / "exports").is_dir()


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    s = AppSettings(
        connection_timeout_s=10.0,
        default_poll_rate_s=15.0,
        bool_display="Off / On",
        filename_template="{ip}_{slot}",
    )
    s.save(path)
    loaded = AppSettings.load(path)
    assert loaded.connection_timeout_s == 10.0
    assert loaded.default_poll_rate_s == 15.0
    assert loaded.bool_display == "Off / On"
    assert loaded.filename_template == "{ip}_{slot}"


def test_load_ignores_unknown_keys(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"connection_timeout_s": 7, "future_field": True}),
        encoding="utf-8",
    )
    s = AppSettings.load(path)
    assert s.connection_timeout_s == 7.0
