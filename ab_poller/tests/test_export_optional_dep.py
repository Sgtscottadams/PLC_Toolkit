from __future__ import annotations

import builtins
import importlib

import pytest


def test_importing_plck_does_not_require_openpyxl(monkeypatch):
    # Launch + discovery must not depend on openpyxl (Excel-only dependency).
    # Simulate openpyxl being absent and confirm the package and its submodules
    # still import cleanly.
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "openpyxl" or name.startswith("openpyxl."):
            raise ModuleNotFoundError("No module named 'openpyxl'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    import plck
    importlib.reload(plck)

    assert hasattr(plck, "discovery")
    assert hasattr(plck, "export")
    assert callable(plck.discovery.discover_tags)
    assert callable(plck.export.export_tags)


def test_excel_export_without_openpyxl_raises_actionable_error(monkeypatch):
    import plck.export as export_mod
    from plck.models import PlcConnection, TagTree

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "openpyxl" or name.startswith("openpyxl."):
            raise ModuleNotFoundError("No module named 'openpyxl'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    tree = TagTree(
        plc=PlcConnection(nickname="Test", ip="192.0.2.10"),
        root=[],
        discovered_at="2026-06-17T00:00:00Z",
    )

    with pytest.raises(RuntimeError, match="openpyxl"):
        export_mod._write_excel(tree, "unused.xlsx")
