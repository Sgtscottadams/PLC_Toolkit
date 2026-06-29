from __future__ import annotations

from pathlib import Path


def test_default_db_path_uses_env_override(monkeypatch, tmp_path):
    from plc_toolkit.app import _default_db_path
    from plc_toolkit.settings_store import AppSettings

    db_path = tmp_path / "scratch" / "plc_data.db"
    monkeypatch.setenv("PLC_TOOLKIT_DB", str(db_path))

    assert _default_db_path(AppSettings()) == db_path


def test_default_outdir_uses_env_override(monkeypatch, tmp_path):
    from plc_toolkit.app import _default_outdir
    from plc_toolkit.settings_store import AppSettings

    outdir = tmp_path / "exports"
    monkeypatch.setenv("PLC_TOOLKIT_OUTDIR", str(outdir))

    assert _default_outdir(AppSettings()) == outdir
    assert outdir.is_dir()


def test_module_entrypoint_exposes_main():
    import plc_toolkit.__main__ as entrypoint
    from plc_toolkit.app import main

    assert entrypoint.main is main
