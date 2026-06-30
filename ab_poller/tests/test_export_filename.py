"""Regression: export filenames use the correct extension.

Bug (2026-06-30): the Excel export wrote files named ``*.excel`` instead of
``*.xlsx`` because the format key ("excel") was used directly as the file
extension. JSON/XML happened to be correct only because their format key
equals their extension.
"""

from __future__ import annotations

from plck.export import export_tags
from plck.models import PlcConnection, TagDataType, TagNode, TagTree


def _tree() -> TagTree:
    return TagTree(
        plc=PlcConnection(nickname="Compressor Skid A", ip="192.0.2.10"),
        root=[TagNode(name="Speed", data_type=TagDataType.DINT)],
        discovered_at="2026-06-30T10:15:00Z",
    )


def test_excel_export_uses_xlsx_extension(tmp_path):
    written = export_tags(_tree(), fmt="excel", out_dir=tmp_path)
    assert len(written) == 1
    assert written[0].suffix == ".xlsx", f"expected .xlsx, got {written[0].name}"
    assert written[0].is_file()


def test_json_export_uses_json_extension(tmp_path):
    written = export_tags(_tree(), fmt="json", out_dir=tmp_path)
    assert written[0].suffix == ".json"
    assert written[0].is_file()


def test_xml_export_uses_xml_extension(tmp_path):
    written = export_tags(_tree(), fmt="xml", out_dir=tmp_path)
    assert written[0].suffix == ".xml"
    assert written[0].is_file()
