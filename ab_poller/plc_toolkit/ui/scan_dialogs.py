"""Read-only dialogs for browsing and comparing saved tag scans."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from plck.db import DatabaseManager
from plck.models import TagNode, TagTree
from plck.tag_display import format_type_label
from plc_toolkit.time_format import format_scan_timestamp_long


def _add_tree_node(
    parent_item,
    node: TagNode,
    values: Optional[dict[str, object]] = None,
) -> QTreeWidgetItem:
    item = QTreeWidgetItem(parent_item)
    item.setText(0, node.name.rsplit(".", 1)[-1])
    item.setText(1, format_type_label(node))
    if not node.members:
        val = (values or {}).get(node.name)
        item.setText(2, repr(val) if val is not None else "—")
    else:
        item.setText(2, "—")
    item.setToolTip(0, node.name)
    if node.members:
        for member in node.members:
            _add_tree_node(item, member, values)
    return item


def _populate_tag_tree(
    widget: QTreeWidget,
    tree: TagTree,
    values: Optional[dict[str, object]] = None,
) -> None:
    widget.clear()
    for top in tree.root:
        _add_tree_node(widget, top, values)
    widget.collapseAll()


class ScanBrowseDialog(QDialog):
    """Show the tag tree from a saved scan (read-only)."""

    def __init__(
        self,
        tree: TagTree,
        scan_label: str = "",
        values: Optional[dict[str, object]] = None,
        parent: Optional[QDialog] = None,
    ) -> None:
        super().__init__(parent)
        title = "Saved scan tags"
        if scan_label:
            title = f"Saved scan — {scan_label}"
        self.setWindowTitle(title)
        self.resize(780, 520)

        n_values = len(values or {})
        scan_line = format_scan_timestamp_long(scan_label) if scan_label else ""
        parts = [
            f"{tree.leaf_count()} leaf tag(s) · {tree.count()} total node(s)",
        ]
        if scan_line and scan_line != "—":
            parts.insert(0, f"Scan time: {scan_line}")
        if n_values:
            parts.append(f"{n_values} saved value(s)")
        hint = QLabel(" · ".join(parts))
        hint.setObjectName("hint")

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tag", "Type", "Value"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        h = self.tree.header()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.Interactive)
        h.setSectionResizeMode(1, QHeaderView.Interactive)
        h.setSectionResizeMode(2, QHeaderView.Interactive)
        _populate_tag_tree(self.tree, tree, values)
        for col in range(3):
            self.tree.resizeColumnToContents(col)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.Close).clicked.connect(self.accept)

        lay = QVBoxLayout(self)
        lay.addWidget(hint)
        lay.addWidget(self.tree, 1)
        lay.addWidget(buttons)


class ScanCompareDialog(QDialog):
    """Compare leaf tags between two saved scans."""

    _COL_TAG = 0
    _COL_OLDER = 1
    _COL_NEWER = 2
    _COL_STATUS = 3

    def __init__(
        self,
        db: DatabaseManager,
        scan_id_a: int,
        scan_id_b: int,
        label_a: str,
        label_b: str,
        parent: Optional[QDialog] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Compare scans")
        self.resize(900, 560)

        tree_a = db.load_scan(scan_id_a)
        tree_b = db.load_scan(scan_id_b)
        if tree_a is None or tree_b is None:
            raise ValueError("Could not load one or both scans for comparison.")

        if label_a <= label_b:
            older_label, newer_label = label_a, label_b
            older_leaves = set(tree_a.leaf_names())
            newer_leaves = set(tree_b.leaf_names())
        else:
            older_label, newer_label = label_b, label_a
            older_leaves = set(tree_b.leaf_names())
            newer_leaves = set(tree_a.leaf_names())

        hint = QLabel(
            f"Older scan: {older_label} ({len(older_leaves)} leaves) · "
            f"Newer scan: {newer_label} ({len(newer_leaves)} leaves) · "
            f"Red = removed since older scan · Green = added in newer scan"
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Tag", f"In older ({_short_ts(older_label)})",
             f"In newer ({_short_ts(newer_label)})", "Change"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(self._COL_TAG, QHeaderView.Stretch)
        for col in (self._COL_OLDER, self._COL_NEWER, self._COL_STATUS):
            h.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        all_tags = sorted(older_leaves | newer_leaves)
        self.table.setRowCount(len(all_tags))
        removed = added = unchanged = 0
        for row, tag in enumerate(all_tags):
            in_older = tag in older_leaves
            in_newer = tag in newer_leaves
            self.table.setItem(row, self._COL_TAG, QTableWidgetItem(tag))
            self.table.setItem(
                row, self._COL_OLDER,
                QTableWidgetItem("yes" if in_older else "—"),
            )
            self.table.setItem(
                row, self._COL_NEWER,
                QTableWidgetItem("yes" if in_newer else "—"),
            )
            if in_older and in_newer:
                status = "Unchanged"
                unchanged += 1
                bg = None
            elif in_older:
                status = "Removed"
                removed += 1
                bg = QColor("#5c2a2a")
            else:
                status = "Added"
                added += 1
                bg = QColor("#2a5c2a")
            status_item = QTableWidgetItem(status)
            self.table.setItem(row, self._COL_STATUS, status_item)
            if bg is not None:
                for col in range(4):
                    cell = self.table.item(row, col)
                    if cell is not None:
                        cell.setBackground(bg)

        summary = QLabel(
            f"{len(all_tags)} tag(s): {unchanged} unchanged, "
            f"{added} added, {removed} removed"
        )
        summary.setObjectName("hint")

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).clicked.connect(self.accept)

        lay = QVBoxLayout(self)
        lay.addWidget(hint)
        lay.addWidget(summary)
        lay.addWidget(self.table, 1)
        lay.addWidget(buttons)


def _short_ts(ts: str) -> str:
    """Trim ISO timestamp for column headers."""
    return ts.replace("T", " ").replace("Z", "")[:19]
