"""plck.export — Write a TagTree to Excel, JSON, or XML.

The output shape matches what the v1 TUI's `export_to_*` methods
produced (verified against `plc_toolkit_consolidated.py:349-435`), so
existing operators' downstream tooling keeps working unchanged.

    Excel:  one sheet per top-level UDT, all tags flattened.
            First sheet is an index of the PLC + timestamp.
    JSON:   nested object preserving UDT structure.
    XML:    CIP-style tag path per element (uses ':' as the path
            separator because the Logix Designer XML format does).

Usage:
    from plck.export import export_tags
    written = export_tags(tree, fmt="excel", out_dir=Path("plc_scans"))
    print(written)  # [Path("plc_scans/CompressorSkidA_2026-06-16_1015.xlsx")]
"""

from __future__ import annotations

import json
import re
import xml.dom.minidom
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from plck.models import TagDataType, TagNode, TagTree


ExportFormat = Literal["excel", "json", "xml"]

# File extension per export format. "excel" must map to "xlsx" — the format
# key is not the file extension (the bug this prevents wrote ".excel" files).
_EXT_BY_FORMAT: dict[str, str] = {"excel": "xlsx", "json": "json", "xml": "xml"}


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(nickname: str, when: str, ext: str) -> str:
    """Build a deterministic filename like 'CompressorSkidA_2026-06-16_1015.xlsx'.

    Replaces spaces and unsafe chars with underscores. Matches the v1
    TUI's filename pattern.
    """
    safe = _SAFE_NAME_RE.sub("_", nickname).strip("_") or "plc"
    # when is 'YYYY-MM-DDTHH:MM:SSZ'; we want 'YYYY-MM-DD_HHMM'
    date, _, time_ = when.partition("T")
    time_ = time_.rstrip("Z").replace(":", "")[:4]
    return f"{safe}_{date}_{time_}.{ext}"


def export_tags(
    tree: TagTree,
    fmt: ExportFormat,
    out_dir: Path,
    base_name: Optional[str] = None,
) -> list[Path]:
    """Export a tag tree to a single file in the requested format.

    Returns the list of written files (1 for any single format). The
    caller is responsible for creating `out_dir` if needed (this
    function does it for convenience).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = base_name or safe_filename(
        tree.plc.nickname, tree.discovered_at, ext=_EXT_BY_FORMAT.get(fmt, fmt),
    )
    if fmt == "excel":
        return [_write_excel(tree, out_dir / name)]
    if fmt == "json":
        return [_write_json(tree, out_dir / name)]
    if fmt == "xml":
        return [_write_xml(tree, out_dir / name)]
    raise ValueError(f"Unknown export format: {fmt!r}")


# -- JSON ----------------------------------------------------------------


def _write_json(tree: TagTree, path: Path) -> Path:
    """JSON: nested object. Root is a dict with metadata + tags list."""
    payload = {
        "plc": {
            "nickname": tree.plc.nickname,
            "ip": tree.plc.ip,
            "slot": tree.plc.slot,
            "port": tree.plc.port,
            "cip_path": tree.plc.cip_path,
            "product_name": tree.plc.product_name,
            "revision": tree.plc.revision,
            "serial_number": tree.plc.serial_number,
        },
        "discovered_at": tree.discovered_at,
        "discovery_duration_s": tree.discovery_duration_s,
        "tag_count": tree.count(),
        "leaf_count": tree.leaf_count(),
        "tags": [_json_node(n) for n in tree.root],
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def _json_node(node: TagNode) -> dict:
    out: dict = {
        "name": node.name,
        "data_type": node.data_type.value,
    }
    if node.udt_name:
        out["udt_name"] = node.udt_name
    if node.is_array:
        out["is_array"] = True
        out["array_dim"] = list(node.array_dim)
    if node.members:
        out["members"] = [_json_node(m) for m in node.members]
    return out


# -- XML -----------------------------------------------------------------


def _write_xml(tree: TagTree, path: Path) -> Path:
    """XML: CIP-style tag path per element, structure preserved.

    Uses ':' as the path separator to match the Logix Designer export
    convention. Top-level tag is the <Tags> root; each tag is a
    <Tag name=... data_type=...> element with nested children.

    Includes a <Plc> header with metadata so the file is
    self-describing.
    """
    root = ET.Element("TagTree")
    plc = ET.SubElement(root, "Plc")
    ET.SubElement(plc, "Nickname").text = tree.plc.nickname
    ET.SubElement(plc, "IP").text = tree.plc.ip
    ET.SubElement(plc, "Slot").text = str(tree.plc.slot)
    ET.SubElement(plc, "Port").text = str(tree.plc.port)
    if tree.plc.cip_path:
        ET.SubElement(plc, "CIPPath").text = tree.plc.cip_path
    if tree.plc.product_name:
        ET.SubElement(plc, "ProductName").text = tree.plc.product_name
    if tree.plc.revision:
        ET.SubElement(plc, "Revision").text = tree.plc.revision
    if tree.plc.serial_number:
        ET.SubElement(plc, "SerialNumber").text = tree.plc.serial_number
    ET.SubElement(plc, "DiscoveredAt").text = tree.discovered_at
    ET.SubElement(plc, "TagCount").text = str(tree.count())

    tags = ET.SubElement(root, "Tags")
    for node in tree.root:
        tags.append(_xml_node(node))

    raw = ET.tostring(root, encoding="utf-8")
    pretty = xml.dom.minidom.parseString(raw).toprettyxml(indent="  ", encoding="UTF-8")
    path.write_bytes(pretty)
    return path


def _xml_node(node: TagNode) -> ET.Element:
    el = ET.Element("Tag")
    el.set("name", node.name)
    el.set("data_type", node.data_type.value)
    if node.udt_name:
        el.set("udt_name", node.udt_name)
    if node.is_array:
        el.set("is_array", "true")
        el.set("array_dim", ",".join(str(d) for d in node.array_dim))
    for m in node.members:
        el.append(_xml_node(m))
    return el


# -- Excel ---------------------------------------------------------------


def _require_openpyxl():
    """Import openpyxl lazily.

    openpyxl is an Excel-only dependency. Launch, discovery, monitoring, and
    JSON/XML export must not depend on it. Importing it here keeps the GUI
    startable without openpyxl installed and turns a missing dependency into
    an actionable error only when the operator actually exports to Excel.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "Excel export requires the 'openpyxl' package, which is not "
            "installed in this environment. Install it with "
            "`pip install openpyxl` (or `pip install -r requirements.txt`), "
            "or export to JSON/XML instead."
        ) from e
    return Workbook, Font, PatternFill


def _write_excel(tree: TagTree, path: Path) -> Path:
    """Excel: index sheet (PLC metadata) + one sheet per top-level UDT,
    all tags flattened."""
    Workbook, Font, PatternFill = _require_openpyxl()
    header_fill = PatternFill("solid", fgColor="1F3A5F")
    header_font = Font(bold=True, color="FFFFFF")
    bold = Font(bold=True)
    meta_fill = PatternFill("solid", fgColor="F0F4F8")
    wb = Workbook()

    # Index sheet.
    idx = wb.active
    idx.title = "PLC"
    rows = [
        ("Nickname", tree.plc.nickname),
        ("IP", tree.plc.ip),
        ("Slot", str(tree.plc.slot)),
        ("Port", str(tree.plc.port)),
        ("CIP Path", tree.plc.cip_path or "(slot only)"),
        ("Product Name", tree.plc.product_name or ""),
        ("Revision", tree.plc.revision or ""),
        ("Serial Number", tree.plc.serial_number or ""),
        ("Discovered At", tree.discovered_at),
        ("Discovery Duration (s)", f"{tree.discovery_duration_s:.2f}"),
        ("Tag Count", str(tree.count())),
        ("Leaf Count", str(tree.leaf_count())),
    ]
    for r, (k, v) in enumerate(rows, start=1):
        c1 = idx.cell(row=r, column=1, value=k)
        c2 = idx.cell(row=r, column=2, value=v)
        c1.font = bold
        c1.fill = meta_fill
    idx.column_dimensions["A"].width = 22
    idx.column_dimensions["B"].width = 36

    # One sheet per top-level tag.
    for node in tree.root:
        sheet_name = _safe_sheet_name(node.name)
        ws = wb.create_sheet(title=sheet_name)
        _write_excel_sheet(ws, node, header_font, header_fill)

    wb.save(path)
    return path


def _safe_sheet_name(name: str) -> str:
    """Excel sheet names are max 31 chars, no []:*?/\\."""
    s = re.sub(r"[\[\]:\*?/\\]", "_", name)
    return s[:31] or "Tag"


def _write_excel_sheet(ws, node: TagNode, header_font, header_fill) -> None:
    """Write a tag (and its flattened descendants) to a single sheet.

    Columns: Tag Path, Data Type, UDT Name, Is Array, Array Dim, Is Write Tag
    """
    headers = ["Tag Path", "Data Type", "UDT Name", "Is Array", "Array Dim", "Is Write Tag"]
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = header_font
        cell.fill = header_fill
    row = 1
    for ln in node.walk():
        row += 1
        ws.cell(row=row, column=1, value=ln.name)
        ws.cell(row=row, column=2, value=ln.data_type.value)
        ws.cell(row=row, column=3, value=ln.udt_name or "")
        ws.cell(row=row, column=4, value="Yes" if ln.is_array else "No")
        ws.cell(row=row, column=5, value=",".join(str(d) for d in ln.array_dim) if ln.array_dim else "")
        ws.cell(row=row, column=6, value="Yes" if ln.is_write_tag else "No")
    # Column widths
    widths = {1: 50, 2: 18, 3: 28, 4: 8, 5: 14, 6: 12}
    for col, w in widths.items():
        ws.column_dimensions[chr(64 + col)].width = w
    ws.freeze_panes = "A2"


# -- Monitor history export ----------------------------------------------


def export_monitor_history(
    watch: dict[str, dict],
    *,
    nickname: str,
    out_dir: Path,
    base_name: Optional[str] = None,
) -> list[Path]:
    """Write monitor watch-list metadata and collected samples.

    Produces one ``.xlsx`` workbook with **Tags** and **History** worksheets.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = base_name or _monitor_history_basename(nickname)
    xlsx_path = out_dir / f"{stem}.xlsx"

    history_rows = _monitor_history_rows(watch)
    _write_monitor_history_excel(watch, history_rows, xlsx_path)
    return [xlsx_path]


def _monitor_history_basename(nickname: str) -> str:
    when = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    safe = _SAFE_NAME_RE.sub("_", nickname).strip("_") or "plc"
    date, _, time_ = when.partition("T")
    time_ = time_.rstrip("Z").replace(":", "")[:4]
    return f"{safe}_monitor_history_{date}_{time_}"


def _monitor_history_rows(watch: dict[str, dict]) -> list[tuple[str, str, float]]:
    """Long-format rows sorted by timestamp then tag name."""
    rows: list[tuple[str, str, float]] = []
    for tag in sorted(watch.keys()):
        entry = watch[tag]
        times = list(entry.get("sample_times") or [])
        samples = list(entry.get("samples") or [])
        n = min(len(times), len(samples))
        for i in range(n):
            try:
                rows.append((times[i], tag, float(samples[i])))
            except (TypeError, ValueError):
                continue
    rows.sort(key=lambda r: (r[0], r[1]))
    return rows


def _write_monitor_history_excel(
    watch: dict[str, dict],
    history_rows: list[tuple[str, str, float]],
    path: Path,
) -> Path:
    Workbook, Font, PatternFill = _require_openpyxl()
    header_fill = PatternFill("solid", fgColor="1F3A5F")
    header_font = Font(bold=True, color="FFFFFF")
    wb = Workbook()

    tags_ws = wb.active
    tags_ws.title = "Tags"
    tag_headers = ["Tag", "Data Type", "Last Value", "Last Quality", "Sample Count"]
    for c, h in enumerate(tag_headers, start=1):
        cell = tags_ws.cell(row=1, column=c, value=h)
        cell.font = header_font
        cell.fill = header_fill
    for r, tag in enumerate(sorted(watch.keys()), start=2):
        entry = watch[tag]
        tags_ws.cell(row=r, column=1, value=tag)
        tags_ws.cell(row=r, column=2, value=entry.get("data_type") or "?")
        tags_ws.cell(row=r, column=3, value=entry.get("last_value"))
        tags_ws.cell(row=r, column=4, value=entry.get("last_quality") or "—")
        tags_ws.cell(
            row=r, column=5,
            value=min(
                len(entry.get("samples") or []),
                len(entry.get("sample_times") or []),
            ),
        )
    tags_ws.column_dimensions["A"].width = 48
    tags_ws.column_dimensions["B"].width = 16
    tags_ws.freeze_panes = "A2"

    hist_ws = wb.create_sheet(title="History")
    hist_headers = ["Timestamp", "Tag", "Value"]
    for c, h in enumerate(hist_headers, start=1):
        cell = hist_ws.cell(row=1, column=c, value=h)
        cell.font = header_font
        cell.fill = header_fill
    for r, (ts, tag, val) in enumerate(history_rows, start=2):
        hist_ws.cell(row=r, column=1, value=ts)
        hist_ws.cell(row=r, column=2, value=tag)
        hist_ws.cell(row=r, column=3, value=val)
    hist_ws.column_dimensions["A"].width = 22
    hist_ws.column_dimensions["B"].width = 48
    hist_ws.freeze_panes = "A2"

    wb.save(path)
    return path
