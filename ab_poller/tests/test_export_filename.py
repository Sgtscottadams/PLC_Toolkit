"""Regression: export filenames use the correct extension.

Bug (2026-06-30): the Excel export wrote files named ``*.excel`` instead of
``*.xlsx`` because the format key ("excel") was used directly as the file
extension. JSON/XML happened to be correct only because their format key
equals their extension.
"""

from __future__ import annotations

from plck.export import export_monitor_history, export_tags, render_filename
from plck.models import PlcConnection, TagDataType, TagNode, TagTree


def _tree() -> TagTree:
    return TagTree(
        plc=PlcConnection(nickname="Compressor Skid A", ip="192.0.2.10"),
        root=[TagNode(name="Speed", data_type=TagDataType.DINT)],
        discovered_at="2026-06-30T10:15:00Z",
    )


def _udt_tree() -> TagTree:
    udt = TagNode(name="PIT204", data_type=TagDataType.UDT, udt_name="PRESSURE")
    udt.members = [
        TagNode(name="PIT204.PV", data_type=TagDataType.REAL),
        TagNode(name="PIT204.SP", data_type=TagDataType.REAL),
    ]
    return TagTree(
        plc=PlcConnection(nickname="Skid", ip="192.0.2.10"),
        root=[TagNode(name="Speed", data_type=TagDataType.DINT), udt],
        discovered_at="2026-06-30T10:15:00Z",
    )


def test_excel_export_uses_xlsx_extension(tmp_path):
    written = export_tags(_tree(), fmt="excel", out_dir=tmp_path)
    assert len(written) == 1
    assert written[0].suffix == ".xlsx", f"expected .xlsx, got {written[0].name}"
    assert written[0].is_file()


def test_excel_is_single_flattened_tags_sheet(tmp_path):
    from openpyxl import load_workbook

    written = export_tags(_udt_tree(), fmt="excel", out_dir=tmp_path)[0]
    wb = load_workbook(written)
    # One workbook: a PLC metadata sheet + a single 'Tags' sheet — NOT one
    # sheet per UDT.
    assert wb.sheetnames == ["PLC", "Tags"]
    ws = wb["Tags"]
    headers = [c.value for c in ws[1]]
    assert headers[:3] == ["Level", "Tag", "Data Type"]
    # All tags flattened into this one sheet, in tree order with depth.
    rows = [(r[0].value, r[1].value) for r in ws.iter_rows(min_row=2)]
    tags = [name for _lvl, name in rows]
    assert tags == ["Speed", "PIT204", "PIT204.PV", "PIT204.SP"]
    levels = {name: lvl for lvl, name in rows}
    assert levels["PIT204"] == 0 and levels["PIT204.PV"] == 1


def test_json_export_uses_json_extension(tmp_path):
    written = export_tags(_tree(), fmt="json", out_dir=tmp_path)
    assert written[0].suffix == ".json"
    assert written[0].is_file()


def test_xml_export_uses_xml_extension(tmp_path):
    written = export_tags(_tree(), fmt="xml", out_dir=tmp_path)
    assert written[0].suffix == ".xml"
    assert written[0].is_file()


# -- filename template ---------------------------------------------------

_TMPL = "{ip}_{nickname}_{YYYY-MM-DD}_{HHmm}"


def test_render_filename_includes_ip_with_dashes():
    name = render_filename(
        _TMPL, ip="10.250.5.123", nickname="Skid A", slot=0,
        when_iso="2026-06-30T15:15:00Z",  # 10:15 Central (CDT)
    )
    assert name.startswith("10-250-5-123_")
    assert "Skid_A" in name
    assert "2026-06-30" in name
    assert name.endswith("_1015")


def test_render_filename_blank_nickname_collapses():
    name = render_filename(
        _TMPL, ip="10.250.5.123", nickname="", slot=0,
        when_iso="2026-06-30T15:15:00Z",
    )
    # No leftover double underscore where the nickname was.
    assert "__" not in name
    assert name == "10-250-5-123_2026-06-30_1015"


def test_export_tags_applies_template(tmp_path):
    tree = TagTree(
        plc=PlcConnection(nickname="", ip="10.250.5.123"),
        root=[TagNode(name="Speed", data_type=TagDataType.DINT)],
        discovered_at="2026-06-30T15:15:00Z",
    )
    written = export_tags(
        tree, fmt="json", out_dir=tmp_path, filename_template=_TMPL,
    )[0]
    assert written.name == "10-250-5-123_2026-06-30_1015.json"


def test_export_worker_writes_files(tmp_path):
    from plc_toolkit.workers import ExportWorker

    worker = ExportWorker(
        out_dir=tmp_path, tree=_tree(), tree_formats=["json", "xml"],
    )
    # execute() is the synchronous path the worker thread runs.
    written, errors = worker.execute()
    assert errors == []
    assert {p.suffix for p in written} == {".json", ".xml"}
    assert all(p.is_file() for p in written)


def test_monitor_history_has_plc_sheet(tmp_path):
    from openpyxl import load_workbook

    watch = {
        "PIT204.PV": {
            "data_type": "REAL", "last_value": 42.0, "last_quality": "Good",
            "samples": [42.0], "sample_times": ["2026-06-30 - 10:00:00"],
        }
    }
    plc = PlcConnection(nickname="Skid", ip="10.250.5.123", product_name="1769-L33ER")
    written = export_monitor_history(
        watch, out_dir=tmp_path, plc=plc, filename_template=_TMPL,
    )[0]
    wb = load_workbook(written)
    assert wb.sheetnames == ["PLC", "Tags", "History"]
    plc_vals = {wb["PLC"].cell(row=r, column=1).value: wb["PLC"].cell(row=r, column=2).value
                for r in range(1, wb["PLC"].max_row + 1)}
    assert plc_vals["IP"] == "10.250.5.123"
    assert written.name.startswith("10-250-5-123_") and written.name.endswith("_monitor_history.xlsx")
