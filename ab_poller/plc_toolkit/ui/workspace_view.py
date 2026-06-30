"""Workspace view — the 5-tab inside-the-PLC view.

Tabs:
    Browse       — searchable tag tree + inspector right pane
    Monitor      — multi-tag live table with sparklines (60 samples each)
    Export       — write current tree (or watch list) to Excel/JSON/XML
    History      — list past scans, load a snapshot, see per-scan metadata
    Diagnostics  — connection summary + read history + clear log

A single QThread (`discovery_thread`) runs the discovery; a single
QThread (`monitor_thread`) runs the monitor poll. Both are owned by
this view and are stopped on Disconnect.

The "PLC client" lives only on the worker threads. The UI thread
never holds a pylogix handle.
"""

from __future__ import annotations

import os
import re
import time
from collections import deque
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox,
    QFileDialog, QFormLayout,
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QProgressDialog,
    QPushButton, QRadioButton,
    QSplitter, QSizePolicy,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

import plck
from plck.comms import PLCClient
from plck.db import DatabaseManager
from plck.device_filter import unsupported_device_message
from plck.errors import PlcError
from plck.models import PlcConnection, ReadResult, TagDataType, TagNode, TagTree
from plck.tag_display import format_type_label

from plc_toolkit.settings_store import AppSettings
from plc_toolkit.time_format import (
    format_monitor_trend_span,
    format_scan_timestamp,
    monitor_sample_timestamp,
)
from plc_toolkit.ui.brand_header import BrandHeader
from plc_toolkit.ui.browse_search import BrowseSearchBox
from plc_toolkit.ui.chart_dialog import MonitorChartDialog, TagChartDialog
from plc_toolkit.ui.checkbox_cell import CenteredCheckBoxCell
from plc_toolkit.worker_lifecycle import disconnect_worker_signals
from plc_toolkit.ui.scan_dialogs import ScanBrowseDialog, ScanCompareDialog
from plc_toolkit.workers import (
    DiscoveryWorker, ExportWorker, InspectorWorker, MonitorWorker,
    TreeValuePopulator,
)

try:
    import pylogix
    _PYLOGIX_VERSION = getattr(pylogix, "__version__", "unknown")
except ImportError:
    _PYLOGIX_VERSION = "not installed"


# -- Helper: a small sparkline widget ------------------------------------


class SparklineWidget(QFrame):
    """A tiny sparkline for a numeric value's recent history.

    The widget is fixed-height and updates via `update_value(value)`.
    Internally holds a deque of recent samples.
    """

    def __init__(self, maxlen: int = 60, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(120)
        self.setMinimumHeight(28)
        self.setMaximumHeight(28)
        self._samples: deque = deque(maxlen=maxlen)
        self._last_value: Optional[float] = None
        self._bg = QColor("#1E1E1E")
        self._fg = QColor("#4ECB73")

    def update_value(self, value) -> None:
        if value is None:
            return
        try:
            v = float(value)
        except (TypeError, ValueError):
            return
        self._last_value = v
        self._samples.append(v)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg)
        if len(self._samples) < 2:
            p.end()
            return
        samples = list(self._samples)
        lo = min(samples)
        hi = max(samples)
        rng = hi - lo or 1.0
        n = len(samples)
        w = self.width() - 2
        h = self.height() - 4
        pen = QPen(self._fg)
        pen.setWidth(1)
        p.setPen(pen)
        for i in range(1, n):
            x0 = 1 + int((i - 1) * w / (n - 1))
            x1 = 1 + int(i * w / (n - 1))
            y0 = 2 + int(h - (samples[i - 1] - lo) / rng * h)
            y1 = 2 + int(h - (samples[i] - lo) / rng * h)
            p.drawLine(x0, y0, x1, y1)
        p.end()


# -- Browse tab -----------------------------------------------------------


class BrowseTab(QWidget):
    """The Browse tab: tag tree on the left, inspector on the right."""

    # Qt.UserRole carries the full tag path; these carry node metadata.
    _ROLE_PATH = Qt.UserRole
    _ROLE_IS_LEAF = Qt.UserRole + 1
    _ROLE_IS_WRITE = Qt.UserRole + 2
    _ROLE_IS_BITWORD = Qt.UserRole + 3

    # Emitted when the operator clicks "+ Add to Monitor" in the inspector.
    add_to_monitor_requested = Signal(str)  # full tag path
    # Emitted when the operator clicks "Add to monitor + navigate" in the
    # inspector — same as add but also switches to the Monitor tab.
    navigate_to_monitor_requested = Signal(str)  # full tag path
    # Emitted when the operator clicks the "−" button in the tree to
    # remove a tag from the monitor.
    remove_from_monitor_requested = Signal(str)  # full tag path
    scan_values_ready = Signal(dict)  # tag path -> value after discovery read

    _COL_TAG = 0
    _COL_TYPE = 1
    _COL_VALUE = 2
    _COL_MONITOR = 3

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tree_widget: Optional[QTreeWidget] = None
        self._inspector_widget: Optional[QWidget] = None
        self._inspector_worker: Optional[InspectorWorker] = None
        self._value_populator: Optional[TreeValuePopulator] = None
        self._populator_order: list[str] = []
        self._plc: Optional[PlcConnection] = None
        self._collected_values: dict = {}
        self._total_nodes = 0
        self._total_leaves = 0
        self._all_leaf_tags: list[str] = []
        self._values_loaded: set[str] = set()
        self._priority_tags: set[str] = set()
        # Bit-expanded integer words whose BOOL children are created lazily
        # (on first expand) to keep the tree small/fast. Keyed by tag path.
        self._bitword_nodes: dict[str, TagNode] = {}
        # path -> tree item, so value updates are O(1) instead of walking the
        # whole tree per value (this was a major cost during value population).
        self._item_by_path: dict[str, QTreeWidgetItem] = {}
        self._reprioritize_timer = QTimer(self)
        self._reprioritize_timer.setSingleShot(True)
        self._reprioritize_timer.setInterval(400)
        self._reprioritize_timer.timeout.connect(self._reprioritize_value_poll)

        # -- Search ------------------------------------------------------
        self.search_box = BrowseSearchBox()
        self.search_input = self.search_box.input
        self.search_input.setPlaceholderText(
            "Filter tags… (e.g. PIT*, Facility* — comma separates terms)"
        )
        # Debounce filtering: re-filtering the whole tree on every keystroke
        # froze typing on large PLCs. Run once typing pauses.
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(250)
        self._filter_timer.timeout.connect(
            lambda: self._on_filter_changed(self.search_input.text())
        )
        self.search_input.textChanged.connect(lambda *_: self._filter_timer.start())
        self.count_label = QLabel("0 nodes")
        self.count_label.setObjectName("hint")

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search:"))
        search_row.addWidget(self.search_box, 1)
        search_row.addWidget(self.count_label)

        # -- Tree --------------------------------------------------------
        # Expand/collapse controls for UDT-heavy tag trees.
        tree_toolbar = QHBoxLayout()
        expand_all_btn = QPushButton("Expand all")
        collapse_all_btn = QPushButton("Collapse all")
        tree_toolbar.addWidget(expand_all_btn)
        tree_toolbar.addWidget(collapse_all_btn)
        tree_toolbar.addStretch()
        expand_all_btn.clicked.connect(lambda *_: self._expand_all_except_bits())
        collapse_all_btn.clicked.connect(lambda *_: self.tree.collapseAll())

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tag", "Type", "Value", "Monitor"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        self.tree.itemClicked.connect(self._on_tree_item_clicked)
        self.tree.itemExpanded.connect(self._on_item_expanded_lazy)
        self.tree.itemCollapsed.connect(self._on_item_collapsed_bitword)
        h = self.tree.header()
        h.setStretchLastSection(False)
        h.setMinimumSectionSize(48)
        for col in range(4):
            h.setSectionResizeMode(col, QHeaderView.Interactive)

        # -- Inspector ---------------------------------------------------
        self.inspector = self._build_inspector()

        # -- Discovery progress banner (visible while tag list loads) ----
        self.discovery_banner = QFrame()
        self.discovery_banner.setObjectName("discoveryBanner")
        self.discovery_banner.setStyleSheet(
            "QFrame#discoveryBanner { background: #1D3559; border: 1px solid #1565C0; "
            "border-radius: 4px; padding: 8px; }"
        )
        banner_lay = QVBoxLayout(self.discovery_banner)
        banner_lay.setContentsMargins(12, 10, 12, 10)
        self.discovery_status = QLabel("Discovering tags on the PLC…")
        self.discovery_status.setObjectName("hint")
        self.discovery_status.setWordWrap(True)
        self.discovery_status.setAlignment(Qt.AlignCenter)
        banner_lay.addWidget(self.discovery_status)
        self.discovery_banner.setVisible(False)

        # -- Splitter ----------------------------------------------------
        splitter = QSplitter(Qt.Horizontal)
        tree_container = QWidget()
        tc_lay = QVBoxLayout(tree_container)
        tc_lay.setContentsMargins(0, 0, 0, 0)
        tc_lay.addLayout(search_row)
        tc_lay.addLayout(tree_toolbar)
        tc_lay.addWidget(self.discovery_banner)
        tc_lay.addWidget(self.tree, 1)
        splitter.addWidget(tree_container)
        splitter.addWidget(self.inspector)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([600, 600])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)
        self._tree_widget = self.tree
        self._inspector_widget = self.inspector

    def _build_empty_inspector(self) -> QFrame:
        """Placeholder right pane before the operator selects a tag."""
        stack = QFrame()
        stack.setObjectName("inspectorEmpty")
        empty_lay = QVBoxLayout(stack)
        empty_lay.setAlignment(Qt.AlignCenter)
        empty = QLabel("Select a tag on the left to inspect its value.")
        empty.setObjectName("hint")
        empty.setAlignment(Qt.AlignCenter)
        empty_lay.addWidget(empty)
        return stack

    def _build_inspector(self) -> QWidget:
        """The right-pane inspector. Empty state until a tag is selected."""
        wrap = QFrame()
        wrap.setObjectName("inspectorFrame")
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        self.inspector_stack = self._build_empty_inspector()
        lay.addWidget(self.inspector_stack)
        return wrap

    def reset_inspector(self) -> None:
        """Clear the tag inspector (new PLC connect / disconnect)."""
        self._stop_inspector()
        lay = self.inspector.layout()
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.inspector_stack = self._build_empty_inspector()
        lay.addWidget(self.inspector_stack)
        self.tree.clearSelection()

    def set_plc(self, plc: Optional[PlcConnection]) -> None:
        self._plc = plc
        # Stop any prior inspector.
        self._stop_inspector()

    def prepare_for_new_connection(self) -> None:
        """Drop the prior PLC's tag tree so counts and monitor marks reset."""
        self.reset_inspector()
        self._stop_value_populator()
        self._all_leaf_tags = []
        self._values_loaded = set()
        self._priority_tags = set()
        self._collected_values = {}
        self.tree.clear()
        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)
        self._total_nodes = 0
        self._total_leaves = 0
        self.count_label.setText("Discovering…")

    def set_discovery_active(self, active: bool, message: str = "") -> None:
        """Show or hide the in-tab discovery progress banner."""
        self.discovery_banner.setVisible(active)
        self.tree.setEnabled(not active)
        self.search_input.setEnabled(not active)
        if active:
            self.prepare_for_new_connection()
        if message:
            self.discovery_status.setText(message)
        elif active:
            self.discovery_status.setText(
                "Discovering tags on the PLC…\n"
                "This can take a minute on controllers with many programs."
            )

    def update_discovery_progress(self, message: str) -> None:
        self.discovery_status.setText(message)

    def load_tree(self, tree: TagTree) -> None:
        """Populate the tree from a discovered TagTree."""
        self.set_discovery_active(False)
        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)
        self._total_nodes = tree.count()
        self._total_leaves = tree.leaf_count()
        self._bitword_nodes = {}
        self._item_by_path = {}
        self.tree.clear()
        self.tree.setUpdatesEnabled(False)
        try:
            node_count = 0
            for top in tree.root:
                self._add_tree_node(self.tree, top)
                node_count += 1
                if node_count % 100 == 0:
                    QApplication.processEvents()
        finally:
            self.tree.setUpdatesEnabled(True)
        self.tree.collapseAll()
        self._size_browse_columns()
        self._update_count_label()

    def _update_count_label(self) -> None:
        """Show total node/leaf counts; when filtered, show visible subset."""
        if self._total_nodes <= 0:
            self.count_label.setText("0 nodes")
            return
        terms = self._parse_filter_terms(self.search_input.text())
        if not terms:
            self.count_label.setText(
                f"{self._total_nodes:,} nodes ({self._total_leaves:,} leaves)"
            )
            return
        visible = self._count_visible_nodes()
        self.count_label.setText(
            f"Showing {visible:,} of {self._total_nodes:,} nodes "
            f"({self._total_leaves:,} leaves total)"
        )

    def _count_visible_nodes(self) -> int:
        total = 0

        def walk(item: QTreeWidgetItem) -> None:
            nonlocal total
            if not item.isHidden():
                total += 1
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return total

    def _size_browse_columns(self) -> None:
        """Size browse columns to content; tag column fills remaining width."""
        for col in (self._COL_TYPE, self._COL_VALUE, self._COL_MONITOR):
            self.tree.resizeColumnToContents(col)
        header = self.tree.header()
        viewport_w = max(self.tree.viewport().width(), 400)
        other = sum(header.sectionSize(c) for c in (
            self._COL_TYPE, self._COL_VALUE, self._COL_MONITOR,
        ))
        header.resizeSection(self._COL_TAG, max(160, viewport_w - other - 8))

    def _set_monitor_cell(
        self, item: QTreeWidgetItem, text: str, tooltip: str = "",
    ) -> None:
        col = self._COL_MONITOR
        item.setText(col, text)
        item.setTextAlignment(col, Qt.AlignCenter)
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        item.setFont(col, font)
        if tooltip:
            item.setToolTip(col, tooltip)

    def _add_tree_node(self, parent_item, node: TagNode) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent_item)
        item.setText(self._COL_TAG, node.name.rsplit(".", 1)[-1])
        item.setText(self._COL_TYPE, format_type_label(node))
        # A bit-expanded integer word is both expandable (has BOOL bit
        # children) AND readable (the word value itself), so treat it like a
        # leaf for monitoring/value purposes.
        is_bitword = node.is_bit_word()
        if node.members and not is_bitword:
            for m in node.members:
                self._add_tree_node(item, m)
        elif is_bitword:
            # Bits are revealed on demand: a (+) in the Type column, not an
            # always-visible tree arrow. Children are created only when the
            # operator clicks (+) — keeps the tree small and reads minimal.
            item.setText(self._COL_TYPE, format_type_label(node) + "  (+)")
            self._bitword_nodes[node.name] = node
        item.setText(self._COL_VALUE, "—")
        readable = is_bitword or not node.members
        item.setData(self._COL_TAG, self._ROLE_PATH, node.name)
        self._item_by_path[node.name] = item
        item.setData(self._COL_TAG, self._ROLE_IS_LEAF, readable)
        item.setData(self._COL_TAG, self._ROLE_IS_WRITE, bool(node.is_write_tag))
        item.setData(self._COL_TAG, self._ROLE_IS_BITWORD, is_bitword)
        if node.is_write_tag:
            for c in range(4):
                item.setForeground(c, QColor("#888888"))
        if readable and not node.is_write_tag:
            self._set_monitor_cell(
                item, "+", f"Add {node.name} to monitor",
            )
        return item

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        # Clicking the (+)/(-) in the Type column reveals/hides a word's bits.
        if column == self._COL_TYPE and item.data(
            self._COL_TAG, self._ROLE_IS_BITWORD
        ):
            self._toggle_bits(item)
            return
        if column != self._COL_MONITOR:
            return
        action = item.text(self._COL_MONITOR)
        path = item.data(self._COL_TAG, self._ROLE_PATH)
        if not path:
            return
        is_leaf = bool(item.data(self._COL_TAG, self._ROLE_IS_LEAF))
        is_write = bool(item.data(self._COL_TAG, self._ROLE_IS_WRITE))
        if action == "−":
            self.remove_from_monitor_requested.emit(path)
        elif action == "+" and is_leaf and not is_write:
            self.add_to_monitor_requested.emit(path)

    def _clear_search(self) -> None:
        self.search_input.clear()

    @staticmethod
    def _parse_filter_terms(text: str) -> list[str]:
        return [p.strip().lower() for p in (text or "").split(",") if p.strip()]

    @staticmethod
    def _term_to_regex(term: str) -> re.Pattern[str]:
        if "*" in term:
            pat = "".join(".*" if ch == "*" else re.escape(ch) for ch in term)
        else:
            pat = ".*" + re.escape(term) + ".*"
        return re.compile(pat, re.IGNORECASE)

    def _item_matches_terms(
        self, item: QTreeWidgetItem, terms: list[str],
    ) -> bool:
        path = (
            item.data(self._COL_TAG, self._ROLE_PATH)
            or item.text(self._COL_TAG)
            or ""
        )
        name = item.text(self._COL_TAG)
        typ = item.text(self._COL_TYPE)
        for term in terms:
            regex = self._term_to_regex(term)
            if (
                regex.search(path)
                or regex.search(name)
                or regex.search(typ)
            ):
                return True
        return False

    def _reset_item_visibility(self, item: QTreeWidgetItem) -> None:
        """Recursively unhide every node (used when the filter is cleared)."""
        item.setHidden(False)
        for i in range(item.childCount()):
            self._reset_item_visibility(item.child(i))

    def _show_all_descendants(self, item: QTreeWidgetItem) -> None:
        item.setHidden(False)
        for i in range(item.childCount()):
            self._show_all_descendants(item.child(i))

    def _on_filter_changed(self, text: str) -> None:
        terms = self._parse_filter_terms(text)
        if not terms:
            for i in range(self.tree.topLevelItemCount()):
                self._reset_item_visibility(self.tree.topLevelItem(i))
            self.tree.collapseAll()
        else:
            for i in range(self.tree.topLevelItemCount()):
                self._filter_item(self.tree.topLevelItem(i), terms)
        self._update_count_label()
        self._schedule_reprioritize_value_poll()

    def _visible_leaf_paths(self) -> list[str]:
        """Leaf tag paths currently visible in the tree (respects filter)."""
        out: list[str] = []

        def walk(item: QTreeWidgetItem) -> None:
            if item.isHidden():
                return
            path = item.data(self._COL_TAG, self._ROLE_PATH)
            is_leaf = bool(item.data(self._COL_TAG, self._ROLE_IS_LEAF))
            is_write = bool(item.data(self._COL_TAG, self._ROLE_IS_WRITE))
            if is_leaf and path and not is_write:
                out.append(str(path))
                return
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return out

    def _priority_poll_order(self, tags: list[str]) -> list[str]:
        """Visible / selected tags first; hidden tags still polled afterward."""
        if not tags:
            return []
        order_index = {t: i for i, t in enumerate(tags)}
        selected_missing: set[str] = set()
        items = self.tree.selectedItems()
        if items:
            item = items[0]
            path = item.data(self._COL_TAG, self._ROLE_PATH)
            if path and item.data(self._COL_TAG, self._ROLE_IS_LEAF):
                val = item.text(self._COL_VALUE).strip()
                if val in ("—", "", "(error)"):
                    selected_missing.add(str(path))

        visible: set[str] = set()
        if self._parse_filter_terms(self.search_input.text()):
            visible = set(self._visible_leaf_paths())

        def bucket(tag: str) -> tuple[int, int]:
            if tag in selected_missing:
                return (0, order_index[tag])
            if tag in self._priority_tags:
                return (1, order_index[tag])
            if tag in visible:
                return (2, order_index[tag])
            return (3, order_index[tag])

        return sorted(tags, key=bucket)

    def _schedule_reprioritize_value_poll(self) -> None:
        if self._value_populator is not None and self._plc is not None:
            self._reprioritize_timer.start()

    def _reprioritize_value_poll(self) -> None:
        if self._plc is None or not self._all_leaf_tags:
            return
        remaining = [
            t for t in self._all_leaf_tags if t not in self._values_loaded
        ]
        if not remaining:
            return
        ordered = self._priority_poll_order(remaining)
        self._start_value_populator(ordered)

    def _filter_item(self, item: QTreeWidgetItem, terms: list[str]) -> bool:
        """Recursively hide items that don't match. Returns True if any
        descendant (or self) matched.

        Comma-separated terms use OR logic (e.g. ``PIT*, Facility*``).

        Supports '*' wildcards (glob-style): 'PIT*' matches any tag
        starting with 'PIT', '*Scale*' matches any tag containing 'Scale'.
        Without wildcards, the default is substring match (same as '*needle*').

        Matching uses the full tag path (not just the short tree label).

        Special rule: if the parent itself matches the filter, ALL children
        are shown (not filtered individually). The operator searched for the
        UDT name and expects to see its full structure. If only a child
        matches, the parent and that child are shown but other non-matching
        siblings are hidden.
        """
        if not terms:
            return True

        self_match = self._item_matches_terms(item, terms)

        # Parent matched: show all descendants unfiltered.
        if self_match:
            self._show_all_descendants(item)
            item.setExpanded(True)
            return True

        # Parent did NOT match — check children recursively.
        child_match = False
        for i in range(item.childCount()):
            if self._filter_item(item.child(i), terms):
                child_match = True
        visible = child_match
        item.setHidden(not visible)
        if visible:
            item.setExpanded(True)
        return visible

    def _on_tree_selection_changed(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        item = items[0]
        full = item.data(0, self._ROLE_PATH)
        if not full:
            return
        is_leaf = bool(item.data(0, self._ROLE_IS_LEAF))
        is_write = bool(item.data(0, self._ROLE_IS_WRITE))
        self._show_inspector(full, is_leaf=is_leaf, is_write=is_write)
        if is_leaf and not is_write:
            val = item.text(self._COL_VALUE).strip()
            if val in ("—", "", "(error)"):
                self._priority_tags.add(str(full))
                self._schedule_reprioritize_value_poll()

    def tag_type(self, tag: str) -> str:
        """Return the data type string for *tag* by searching the tree."""
        for i in range(self.tree.topLevelItemCount()):
            node = self._find_tree_item_by_path(self.tree.topLevelItem(i), tag)
            if node is not None:
                return node.text(1)
        return "?"

    def mark_as_monitored(self, tag: str) -> None:
        """Swap the tree '+' button to '-' indicating the tag is watched."""
        self._set_tree_monitor_button(tag, monitored=True)

    def mark_as_not_monitored(self, tag: str) -> None:
        """Swap the tree '-' button back to '+' indicating the tag is free."""
        self._set_tree_monitor_button(tag, monitored=False)

    def _set_tree_monitor_button(self, tag: str, monitored: bool) -> None:
        for i in range(self.tree.topLevelItemCount()):
            item = self._find_tree_item_by_path(self.tree.topLevelItem(i), tag)
            if item is not None:
                if monitored:
                    self._set_monitor_cell(
                        item, "−", f"Remove {tag} from monitor",
                    )
                else:
                    self._set_monitor_cell(
                        item, "+", f"Add {tag} to monitor",
                    )
                return

    def populate_tree_values(self, plc: PlcConnection, tags: list[str]) -> None:
        """Kick off a one-shot batch read of all leaf tags to auto-fill the
        tree's Value column. The operator sees values appear gradually as each
        batch completes — no need to click every tag."""
        if not tags:
            return
        self._plc = plc
        self._all_leaf_tags = list(tags)
        self._values_loaded = set()
        self._collected_values = {}
        ordered = self._priority_poll_order(tags)
        self._start_value_populator(ordered)

    def _stop_value_populator(self, wait_ms: int = 10000) -> None:
        """Stop the browse value populator and block until the thread exits."""
        pop = self._value_populator
        if pop is None:
            return
        self._value_populator = None
        self._populator_order = []
        disconnect_worker_signals(pop)
        pop.stop()
        if pop.isRunning():
            pop.wait(wait_ms)

    def _start_value_populator(self, tags: list[str]) -> None:
        if not tags or self._plc is None:
            return
        if self._value_populator is not None and self._value_populator.isRunning():
            if tags == self._populator_order:
                return
            self._value_populator.set_tags(tags)
            self._populator_order = list(tags)
            return
        self._stop_value_populator()
        pop = TreeValuePopulator(self._plc, tags, timeout_s=10.0)
        pop.setObjectName("BrowseValuePopulator")
        self._value_populator = pop
        self._populator_order = list(tags)
        pop.signals.chunk_loaded.connect(self._on_value_chunk)
        pop.signals.finished.connect(self._on_value_population_finished)
        pop.start()

    def _on_value_population_finished(self) -> None:
        if self._collected_values:
            self.scan_values_ready.emit(dict(self._collected_values))

    def _show_inspector(self, tag: str, is_leaf: bool = True, is_write: bool = False) -> None:
        """Replace the empty placeholder with a populated inspector for `tag`."""
        self._stop_inspector()

        old = self.inspector.layout().itemAt(0).widget()
        if old is not None:
            old.setParent(None)
            old.deleteLater()

        panel = QFrame()
        panel.setObjectName("inspectorPanel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        # --- Row 1: tag name + type chip + write-tag badge ---------------
        header_row = QHBoxLayout()
        title = QLabel(tag)
        title.setObjectName("inspectorTitle")
        header_row.addWidget(title)
        header_row.addStretch()
        if is_write:
            badge = QLabel("write")
            badge.setObjectName("inspectorWriteBadge")
            badge.setStyleSheet(
                "color: #B8860B; font-size: 9px; padding: 1px 6px; "
                "border: 1px solid #B8860B; border-radius: 2px;"
            )
            header_row.addWidget(badge)
        lay.addLayout(header_row)

        # --- Row 2: metadata (type, quality, read time) -----------------
        meta = QLabel("Quality: ? · last read —")
        meta.setObjectName("inspectorMeta")
        lay.addWidget(meta)

        # --- Hero value --------------------------------------------------
        value_label = QLabel("—")
        value_label.setObjectName("inspectorValue")
        value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        value_label.setMinimumHeight(48)
        lay.addWidget(value_label)

        # --- Sparkline ---------------------------------------------------
        spark = SparklineWidget(maxlen=60)
        spark.setMinimumHeight(42)
        lay.addWidget(spark)

        # --- Recent reads table (last 10 samples) ------------------------
        reads_table = QTableWidget(0, 3)
        reads_table.setHorizontalHeaderLabels(["Time", "Value", "Quality"])
        reads_table.verticalHeader().setVisible(False)
        reads_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        reads_table.setMaximumHeight(140)
        reads_table.setMinimumHeight(80)
        rh = reads_table.horizontalHeader()
        rh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        rh.setSectionResizeMode(1, QHeaderView.Stretch)
        rh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        lay.addWidget(reads_table, 1)

        # --- Actions row -------------------------------------------------
        actions = QHBoxLayout()
        actions.setSpacing(8)
        add_btn = QPushButton("Watch Tag")
        add_btn.setToolTip(
            "Add this tag to the Monitor watch list and switch to the Monitor tab"
        )
        hist_btn = QPushButton("Chart history")
        hist_btn.setToolTip("Open a live trend chart for this tag")
        copy_btn = QPushButton("Copy tag path")
        actions.addWidget(add_btn)
        actions.addWidget(hist_btn)
        actions.addStretch()
        actions.addWidget(copy_btn)
        lay.addLayout(actions)

        self.inspector.layout().addWidget(panel)

        # Stash references.
        panel._meta_label = meta
        panel._value_label = value_label
        panel._spark = spark
        panel._reads_table = reads_table
        panel._tag = tag
        panel._add_btn = add_btn
        panel._hist_btn = hist_btn
        panel._copy_btn = copy_btn
        panel._history = deque(maxlen=120)
        panel._is_leaf = is_leaf
        panel._is_write = is_write

        # Wire action buttons.
        copy_btn.clicked.connect(lambda *_: self._copy_tag_path(tag))
        add_btn.clicked.connect(lambda *_: self.navigate_to_monitor_requested.emit(tag))
        hist_btn.clicked.connect(lambda *_, p=panel: self._show_chart_history(p))

        if is_write:
            add_btn.setEnabled(False)
            add_btn.setToolTip("Write tag — not supported in v2.0 (read-only).")

        if not is_leaf:
            value_label.setText("—")
            meta.setText(
                "Structure/UDT — select an atomic member (e.g. .PV, .Sts) to read."
            )
            add_btn.setEnabled(False)
            add_btn.setToolTip(
                "Select an atomic member of this structure to add to the monitor."
            )
            return

        # Start a 2s inspector poll on a worker thread.
        if self._plc is not None:
            worker = InspectorWorker(self._plc, tag, interval_s=5.0)
            worker.signals.sample.connect(
                lambda r, p=panel: self._on_inspector_sample(p, r)
            )
            worker.signals.failed.connect(
                lambda msg, p=panel: self._on_inspector_failed(p, msg)
            )
            worker.start()
            self._inspector_worker = worker
            panel._worker = worker

    def _on_inspector_sample(self, panel: QFrame, r: ReadResult) -> None:
        panel._history.appendleft(
            (time.strftime("%H:%M:%S"), r.quality.value, r.value, r.error)
        )
        # Keep the most recent 10 entries in the inline table.
        history = list(panel._history)
        tbl = panel._reads_table
        tbl.setRowCount(0)
        tbl.setRowCount(min(len(history), 10))
        for i, (ts, qual, val, err) in enumerate(history[:10]):
            tbl.setItem(i, 0, QTableWidgetItem(ts))
            tbl.setItem(i, 1, QTableWidgetItem(repr(val) if qual == "Good" else (err or "—")))
            tbl.setItem(i, 2, QTableWidgetItem(qual))

        if r.quality.value == "Good":
            panel._value_label.setText(repr(r.value))
            panel._meta_label.setText(
                f"Quality: Good · last read {r.elapsed_ms:.0f}ms ago"
            )
            panel._spark.update_value(r.value)
            # Update the tree's "Value" column for the matching tag.
            self._update_tree_value(panel._tag, r.value)
        else:
            panel._value_label.setText("(error)")
            panel._meta_label.setText(
                f"Quality: Bad — {r.error or 'unknown error'}"
            )

    def _on_inspector_failed(self, panel: QFrame, message: str) -> None:
        panel._history.appendleft(
            (time.strftime("%H:%M:%S"), "Bad", None, message)
        )
        panel._value_label.setText("(read error)")
        panel._meta_label.setText(f"Quality: Bad — {message}")

    def _update_tree_value(self, tag: str, value) -> None:
        """Write the latest value into the tree's 'Value' column for the
        matching tag, so the operator sees live values inline without leaving
        the browse tab."""
        item = self._item_by_path.get(tag)
        if item is None:
            return
        try:
            item.setText(self._COL_VALUE, repr(value))
        except RuntimeError:
            # Item was deleted (tree rebuilt) — drop the stale index entry.
            self._item_by_path.pop(tag, None)
            return
        if item.data(self._COL_TAG, self._ROLE_IS_BITWORD):
            self._set_bit_children_values(item, value)

    def _set_bit_children_values(self, item: QTreeWidgetItem, value) -> None:
        """Derive each BOOL bit's value from the parent integer word — no
        extra PLC reads. Child index i == bit index i."""
        try:
            word = int(value)
        except (TypeError, ValueError):
            return
        for i in range(item.childCount()):
            item.child(i).setText(self._COL_VALUE, str((word >> i) & 1))

    def _expand_all_except_bits(self) -> None:
        """Expand every node EXCEPT bit-expanded integer words. The 8–64 bits
        under a word stay collapsed (a manual click on the word), so this is
        fast even on bit-heavy controllers."""
        self.tree.setUpdatesEnabled(False)
        try:
            for i in range(self.tree.topLevelItemCount()):
                self._expand_item_except_bits(self.tree.topLevelItem(i))
        finally:
            self.tree.setUpdatesEnabled(True)

    def _expand_item_except_bits(self, item: QTreeWidgetItem) -> None:
        if item.data(self._COL_TAG, self._ROLE_IS_BITWORD):
            return  # leave bit-words collapsed; bits expand on manual click
        item.setExpanded(True)
        for i in range(item.childCount()):
            self._expand_item_except_bits(item.child(i))

    def _materialize_bits(self, item: QTreeWidgetItem) -> None:
        """Create a bit-word's BOOL children once, deriving values from the
        word's already-read value (no extra PLC reads)."""
        if item.childCount() > 0:
            return
        path = item.data(self._COL_TAG, self._ROLE_PATH)
        node = self._bitword_nodes.get(str(path)) if path else None
        if node is None:
            return
        self.tree.setUpdatesEnabled(False)
        try:
            for m in node.members:
                self._add_tree_node(item, m)
        finally:
            self.tree.setUpdatesEnabled(True)
        self._set_bit_children_values(item, item.text(self._COL_VALUE).strip())

    def _toggle_bits(self, item: QTreeWidgetItem) -> None:
        """Reveal (first click) or collapse/expand a word's bits."""
        if item.childCount() == 0:
            self._materialize_bits(item)
            item.setExpanded(True)
        else:
            item.setExpanded(not item.isExpanded())
        self._update_bitword_type_label(item)

    def _update_bitword_type_label(self, item: QTreeWidgetItem) -> None:
        path = item.data(self._COL_TAG, self._ROLE_PATH)
        node = self._bitword_nodes.get(str(path)) if path else None
        if node is None:
            return
        base = format_type_label(node)
        marker = "(-)" if (item.childCount() > 0 and item.isExpanded()) else "(+)"
        item.setText(self._COL_TYPE, f"{base}  {marker}")

    def _on_item_expanded_lazy(self, item: QTreeWidgetItem) -> None:
        """Safety net: if a bit-word is expanded via the tree arrow (after it
        has been revealed once), make sure its bits exist and the label syncs."""
        if not item.data(self._COL_TAG, self._ROLE_IS_BITWORD):
            return
        self._materialize_bits(item)
        self._update_bitword_type_label(item)

    def _on_item_collapsed_bitword(self, item: QTreeWidgetItem) -> None:
        if item.data(self._COL_TAG, self._ROLE_IS_BITWORD):
            self._update_bitword_type_label(item)

    def _on_value_chunk(self, results: list[ReadResult]) -> None:
        """Populate tree values from a batch-read chunk. The whole chunk is
        applied under one repaint so value population stays smooth."""
        if self._plc is None:
            return
        self.tree.setUpdatesEnabled(False)
        try:
            for r in results:
                self._values_loaded.add(r.tag_name)
                if r.quality.value == "Good":
                    self._collected_values[r.tag_name] = r.value
                    self._update_tree_value(r.tag_name, r.value)
        finally:
            self.tree.setUpdatesEnabled(True)

    def _find_tree_item_by_path(self, parent, tag: str):
        if parent.data(0, self._ROLE_PATH) == tag:
            return parent
        for i in range(parent.childCount()):
            found = self._find_tree_item_by_path(parent.child(i), tag)
            if found:
                return found
        return None

    def _copy_tag_path(self, tag: str) -> None:
        """Copy the full tag path to the system clipboard."""
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(tag)

    def _show_chart_history(self, panel: QFrame) -> None:
        """Open a live trend chart fed from the inspector's rolling history."""
        TagChartDialog(
            panel._tag,
            history_getter=lambda: list(panel._history),
            parent=self,
        ).exec()

    def _stop_inspector(self) -> None:
        worker = self._inspector_worker
        if worker is None:
            return
        self._inspector_worker = None
        disconnect_worker_signals(worker, names=("sample", "failed", "stopped"))
        worker.stop()
        if worker.isRunning():
            worker.wait(3000)

    def stop_background_workers(self) -> None:
        """Stop browse-side threads (value populator, inspector)."""
        self._reprioritize_timer.stop()
        self._stop_inspector()
        self._stop_value_populator()

    def shutdown(self) -> None:
        self.stop_background_workers()


# -- Monitor tab ----------------------------------------------------------


class MonitorTab(QWidget):
    """Multi-tag live monitoring with sparklines and a Quality column."""

    MONITOR_MAX_TAGS = 500

    _COL_CHART = 0
    _COL_TAG = 1
    _COL_TYPE = 2
    _COL_VALUE = 3
    _COL_QUALITY = 4
    _COL_TREND = 5
    _COL_REMOVE = 6

    add_requested = Signal(str)  # tag path
    remove_requested = Signal(str)  # tag path
    cleared = Signal()

    def __init__(
        self,
        history_samples: int = 60,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._watch: dict[str, dict] = {}
        self._chart_cells: dict[str, CenteredCheckBoxCell] = {}
        self._history_samples = max(10, min(8640, int(history_samples)))
        self._sort_column = self._COL_TAG
        self._sort_ascending = True

        # -- Top controls ------------------------------------------------
        self.interval_combo = QComboBox()
        self.interval_combo.addItems(["2 s", "5 s", "10 s", "30 s", "1 min"])
        self.interval_combo.setCurrentText("5 s")
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setCheckable(True)
        self.pause_btn.toggled.connect(self._on_pause_toggled)
        clear_btn = QPushButton("Clear watch list")
        clear_btn.clicked.connect(self._on_clear)
        self.chart_btn = QPushButton("Open chart")
        self.chart_btn.setToolTip(
            "Check one or more tags in the Chart column, then open a live chart"
        )
        self.chart_btn.setEnabled(False)
        self.chart_btn.clicked.connect(self._on_chart_selected)
        top = QHBoxLayout()
        top.addWidget(QLabel("Poll interval:"))
        top.addWidget(self.interval_combo)
        top.addSpacing(20)
        top.addWidget(self.pause_btn)
        top.addStretch()
        top.addWidget(self.chart_btn)
        top.addWidget(clear_btn)

        monitor_hint = QLabel(
            "Check tags in the Chart column to include them in a live trend chart."
        )
        monitor_hint.setObjectName("hint")
        monitor_hint.setWordWrap(True)

        # -- Empty-state label (only shown when watch list is empty) ----
        self.empty_label = QLabel(
            "Watch list is empty. Use '+ Add to Monitor' from the Browse tab "
            "to start watching a tag live."
        )
        self.empty_label.setObjectName("hint")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setMargin(20)

        # -- Table -------------------------------------------------------
        self.table = QTableWidget(0, 7)
        self._trend_header = "Trend"
        self.table.setHorizontalHeaderLabels(
            ["Chart", "Tag", "Type", "Current value", "Quality",
             self._trend_header, "Remove"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        h = self.table.horizontalHeader()
        h.setStretchLastSection(False)
        h.setMinimumSectionSize(48)
        h.setSectionResizeMode(self._COL_CHART, QHeaderView.Fixed)
        self.table.setColumnWidth(self._COL_CHART, 52)
        h.setSectionResizeMode(self._COL_TAG, QHeaderView.Interactive)
        h.setSectionResizeMode(self._COL_TYPE, QHeaderView.Interactive)
        h.setSectionResizeMode(self._COL_VALUE, QHeaderView.Interactive)
        h.setSectionResizeMode(self._COL_QUALITY, QHeaderView.Interactive)
        h.setSectionResizeMode(self._COL_TREND, QHeaderView.Stretch)
        h.setSectionResizeMode(self._COL_REMOVE, QHeaderView.Interactive)
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_header_clicked)

        # Stack: empty label OR table
        self.stack = QFrame()
        sl = QVBoxLayout(self.stack)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(self.empty_label)
        sl.addWidget(self.table)
        self.table.setVisible(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(top)
        outer.addWidget(monitor_hint)
        outer.addWidget(self.stack)

        self._trend_header_timer = QTimer(self)
        self._trend_header_timer.setInterval(30_000)
        self._trend_header_timer.timeout.connect(self._update_trend_header)
        self._trend_header_timer.start()

    # -- Public API -------------------------------------------------------

    def watch_list(self) -> list[str]:
        return list(self._watch.keys())

    def checked_chart_tags(self) -> list[str]:
        return [
            tag for tag, cell in self._chart_cells.items()
            if cell.is_checked()
        ]

    def series_for_tag(self, tag: str) -> list[tuple[str, float]]:
        entry = self._watch.get(tag)
        if entry is None:
            return []
        times = list(entry.get("sample_times", []))
        vals = list(entry["samples"])
        n = min(len(times), len(vals))
        return [(times[i], vals[i]) for i in range(n)]

    def history_export_payload(self) -> dict[str, dict]:
        """Snapshot of watch-list metadata + samples for export."""
        out: dict[str, dict] = {}
        for tag, entry in self._watch.items():
            out[tag] = {
                "data_type": entry.get("data_type", "?"),
                "last_value": entry.get("last_value"),
                "last_quality": entry.get("last_quality", "—"),
                "samples": list(entry.get("samples") or []),
                "sample_times": list(entry.get("sample_times") or []),
            }
        return out

    def set_history_samples(self, n: int) -> None:
        """Resize per-tag sample deques (Settings → Monitor history depth)."""
        n = max(10, min(8640, int(n)))
        if n == self._history_samples:
            return
        self._history_samples = n
        for entry in self._watch.values():
            old_samples = list(entry.get("samples") or [])
            old_times = list(entry.get("sample_times") or [])
            entry["samples"] = deque(old_samples[-n:], maxlen=n)
            entry["sample_times"] = deque(old_times[-n:], maxlen=n)
        self._update_trend_header()

    def _earliest_sample_time(self) -> str | None:
        earliest: str | None = None
        for entry in self._watch.values():
            times = entry.get("sample_times")
            if not times:
                continue
            first = times[0]
            if earliest is None or first < earliest:
                earliest = first
        return earliest

    def _update_trend_header(self) -> None:
        self._trend_header = format_monitor_trend_span(self._earliest_sample_time())
        self.table.setHorizontalHeaderItem(
            self._COL_TREND, QTableWidgetItem(self._trend_header),
        )

    def add_tag(self, tag: str, data_type: str = "?") -> bool:
        if tag in self._watch:
            return True
        if len(self._watch) >= self.MONITOR_MAX_TAGS:
            QMessageBox.warning(
                self,
                "Watch list full",
                f"The monitor watch list is limited to {self.MONITOR_MAX_TAGS} tags. "
                "Remove tags or export collected history before adding more.",
            )
            return False
        maxlen = self._history_samples
        self._watch[tag] = {
            "last_value": None,
            "last_quality": "—",
            "samples": deque(maxlen=maxlen),
            "sample_times": deque(maxlen=maxlen),
            "data_type": data_type,
        }
        self._rebuild_table()
        self.add_requested.emit(tag)
        return True

    def remove_tag(self, tag: str) -> None:
        self._watch.pop(tag, None)
        self._rebuild_table()
        self.remove_requested.emit(tag)

    def clear_silent(self) -> None:
        """Clear the watch list without a confirmation dialog.

        Used on disconnect so tags from PLC A never bleed into PLC B's
        monitor when the operator connects to a different controller.
        """
        self._watch.clear()
        self._rebuild_table()
        self.cleared.emit()

    def apply_samples(self, results: list[ReadResult]) -> None:
        for r in results:
            entry = self._watch.get(r.tag_name)
            if entry is None:
                continue
            entry["last_value"] = r.value
            entry["last_quality"] = r.quality.value
            if r.quality.value == "Good":
                try:
                    entry["samples"].append(float(r.value))
                    entry["sample_times"].append(monitor_sample_timestamp())
                except (TypeError, ValueError):
                    pass
        self._refresh_table()
        self._update_trend_header()

    def _update_chart_button(self) -> None:
        self.chart_btn.setEnabled(len(self.checked_chart_tags()) > 0)

    def interval_seconds(self) -> float:
        return float(self.interval_combo.currentText().split()[0])

    def is_paused(self) -> bool:
        return self.pause_btn.isChecked()

    # -- Internal --------------------------------------------------------

    def _sorted_watch_items(self) -> list[tuple[str, dict]]:
        """Return watch-list entries in the current sort order."""
        items = list(self._watch.items())

        def sort_key(item: tuple[str, dict]) -> object:
            tag, entry = item
            col = self._sort_column
            if col == self._COL_TAG:
                return tag.lower()
            if col == self._COL_TYPE:
                return str(entry.get("data_type", "?")).lower()
            if col == self._COL_VALUE:
                return repr(entry.get("last_value"))
            if col == self._COL_QUALITY:
                return str(entry.get("last_quality", "—")).lower()
            return tag.lower()

        return sorted(items, key=sort_key, reverse=not self._sort_ascending)

    def _on_header_clicked(self, logical_index: int) -> None:
        if logical_index in (
            self._COL_CHART, self._COL_TREND, self._COL_REMOVE,
        ):
            return
        if logical_index == self._sort_column:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_column = logical_index
            self._sort_ascending = True
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        ordered = self._sorted_watch_items()
        self._watch = dict(ordered)
        n = len(self._watch)
        self._chart_cells.clear()
        self.table.setRowCount(n)
        for r, (tag, entry) in enumerate(self._watch.items()):
            chart_cell = CenteredCheckBoxCell()
            chart_cell.toggled.connect(lambda *_: self._update_chart_button())
            self._chart_cells[tag] = chart_cell
            self.table.setCellWidget(r, self._COL_CHART, chart_cell)
            self.table.setItem(r, self._COL_TAG, QTableWidgetItem(tag))
            self.table.setItem(
                r, self._COL_TYPE, QTableWidgetItem(entry.get("data_type", "?")),
            )
            self.table.setItem(
                r, self._COL_VALUE, QTableWidgetItem(repr(entry["last_value"])),
            )
            self.table.setItem(
                r, self._COL_QUALITY, QTableWidgetItem(entry["last_quality"]),
            )
            spark = SparklineWidget(maxlen=self._history_samples)
            for s in entry["samples"]:
                spark.update_value(s)
            self.table.setCellWidget(r, self._COL_TREND, spark)
            rm_btn = QPushButton("X")
            rm_btn.setFixedSize(32, 22)
            rm_btn.setToolTip(f"Remove {tag} from watch list")
            rm_btn.setStyleSheet("QPushButton { font-weight: bold; padding: 0 4px; }")
            rm_btn.clicked.connect(
                lambda *_, t=tag: self.remove_tag(t)
            )
            self.table.setCellWidget(r, self._COL_REMOVE, rm_btn)
        self._update_chart_button()
        # Show table or empty label.
        if n == 0:
            self.empty_label.setVisible(True)
            self.table.setVisible(False)
        else:
            self.empty_label.setVisible(False)
            self.table.setVisible(True)
            self.table.resizeRowsToContents()

    def _refresh_table(self) -> None:
        for r, (tag, entry) in enumerate(self._watch.items()):
            self.table.item(r, self._COL_VALUE).setText(repr(entry["last_value"]))
            self.table.item(r, self._COL_QUALITY).setText(entry["last_quality"])
            spark = self.table.cellWidget(r, self._COL_TREND)
            if spark is not None and entry["samples"]:
                spark.update_value(entry["samples"][-1])

    def _on_pause_toggled(self, _checked: bool) -> None:
        if self.pause_btn.isChecked():
            self.pause_btn.setText("Resume")
        else:
            self.pause_btn.setText("Pause")

    def _on_clear(self) -> None:
        if not self._watch:
            return
        confirm = QMessageBox.question(
            self, "Clear watch list?",
            f"Remove all {len(self._watch)} tag(s) from the watch list?\n\n"
            f"This does not delete saved tag scans (see the Tag History tab).",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        for tag in list(self._watch.keys()):
            self.remove_tag(tag)
        self.cleared.emit()

    def _on_chart_selected(self) -> None:
        tags = self.checked_chart_tags()
        if not tags:
            QMessageBox.information(
                self, "No tags checked",
                "Check one or more tags in the Chart column, then click Open chart.",
            )
            return
        MonitorChartDialog(
            tags,
            series_getter=self.series_for_tag,
            parent=self,
        ).exec()


# -- Export tab -----------------------------------------------------------


class ExportTab(QWidget):
    """Pick a source, formats, output folder. Run the export."""

    def __init__(
        self,
        default_outdir: Path,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._default_outdir = default_outdir

        # Source (one active at a time)
        self.src_tree = QRadioButton(
            "Current session — full tag tree from the latest discovery"
        )
        self.src_tree.setToolTip(
            "All tags loaded when you connected or re-discovered. "
            "Same list as the Browse tab."
        )
        self.src_tree.setChecked(True)
        self.src_watch = QRadioButton("Monitor watch list only")
        self.src_watch.setToolTip(
            "Only tags currently on the Monitor tab, not the full PLC tag tree."
        )
        self.src_history = QRadioButton("Saved scan from history")
        self.src_history.setToolTip(
            "Export a past scan chosen from the dropdown below."
        )
        self._src_group = QButtonGroup(self)
        self._src_group.addButton(self.src_tree)
        self._src_group.addButton(self.src_watch)
        self._src_group.addButton(self.src_history)
        self.src_history.toggled.connect(self._on_history_source_toggled)
        self.history_scan_combo = QComboBox()
        self.history_scan_combo.setEnabled(False)
        self.history_scan_combo.setMinimumWidth(280)
        self.history_scan_combo.setToolTip(
            "Pick any saved scan for this PLC"
        )
        history_row = QHBoxLayout()
        history_row.setSpacing(12)
        history_row.addWidget(self.src_history)
        history_row.addWidget(self.history_scan_combo, 1)
        src_hint = QLabel(
            "Current session is the tag tree from the latest discovery. "
            "Saved scan uses the dropdown on the same row."
        )
        src_hint.setObjectName("hint")
        src_hint.setWordWrap(True)
        src_box = QFrame()
        sl = QVBoxLayout(src_box)
        sl.addWidget(QLabel("<b>Source</b>"))
        sl.addWidget(self.src_tree)
        sl.addWidget(self.src_watch)
        sl.addLayout(history_row)
        sl.addWidget(src_hint)

        # Formats
        self.fmt_excel = QCheckBox("Excel (.xlsx) — single sheet, all tags tree-flattened")
        self.fmt_json = QCheckBox("JSON — nested object preserving UDT structure")
        self.fmt_xml = QCheckBox("XML — CIP-style tag path per element")
        self.fmt_excel_history = QCheckBox(
            "Excel w/ collected history — Tags + History worksheets (.xlsx)"
        )
        self.fmt_excel_history.setToolTip(
            "Available when source is Monitor watch list only. Exports tag metadata "
            "and every collected sample with Central timestamps for correlation."
        )
        self.fmt_excel_history.setEnabled(False)
        self.fmt_excel.setChecked(True)
        self.fmt_json.setChecked(True)
        fmt_box = QFrame()
        fl = QVBoxLayout(fmt_box)
        fl.addWidget(QLabel("<b>Formats</b>"))
        fl.addWidget(self.fmt_excel)
        fl.addWidget(self.fmt_excel_history)
        fl.addWidget(self.fmt_json)
        fl.addWidget(self.fmt_xml)
        self.src_watch.toggled.connect(self._sync_history_export_option)
        self.src_tree.toggled.connect(self._sync_history_export_option)
        self.src_history.toggled.connect(self._sync_history_export_option)

        # Output folder
        self.outdir_input = QLineEdit(str(default_outdir))
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._on_browse)
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output folder:"))
        out_row.addWidget(self.outdir_input, 1)
        out_row.addWidget(browse_btn)
        out_box = QFrame()
        obl = QVBoxLayout(out_box)
        obl.addLayout(out_row)

        # Filename template
        self.template_input = QLineEdit("{ip}_{nickname}_{YYYY-MM-DD}_{HHmm}")
        self.template_input.setToolTip(
            "Tokens: {nickname}, {ip}, {slot}, {YYYY-MM-DD}, {HHmm}"
        )
        tmpl_box = QFrame()
        tbl = QFormLayout(tmpl_box)
        tbl.addRow("Filename template:", self.template_input)

        # Run button
        self.run_btn = QPushButton("Export")
        self.run_btn.setDefault(True)
        run_row = QHBoxLayout()
        run_row.addStretch()
        run_row.addWidget(self.run_btn)

        # Status
        self.status_label = QLabel("")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(src_box)
        outer.addWidget(fmt_box)
        outer.addWidget(out_box)
        outer.addWidget(tmpl_box)
        outer.addLayout(run_row)
        outer.addWidget(self.status_label)
        outer.addStretch()

    def set_default_outdir(self, path: Path) -> None:
        self._default_outdir = path
        self.outdir_input.setText(str(path))

    def set_filename_template(self, template: str) -> None:
        self.template_input.setText(template)

    def set_history_scans(self, scans: list[dict]) -> None:
        """Populate the saved-scan dropdown (newest first)."""
        current_id = self.selected_history_scan_id()
        self.history_scan_combo.blockSignals(True)
        self.history_scan_combo.clear()
        for s in scans:
            when = format_scan_timestamp(s["scan_timestamp"])
            label = f"{when} · {s['tag_count']} tags"
            self.history_scan_combo.addItem(label, s["id"])
        if current_id is not None:
            idx = self.history_scan_combo.findData(current_id)
            if idx >= 0:
                self.history_scan_combo.setCurrentIndex(idx)
        self.history_scan_combo.blockSignals(False)
        has_scans = self.history_scan_combo.count() > 0
        self.history_scan_combo.setEnabled(
            self.src_history.isChecked() and has_scans
        )

    def selected_history_scan_id(self) -> Optional[int]:
        idx = self.history_scan_combo.currentIndex()
        if idx < 0:
            return None
        data = self.history_scan_combo.itemData(idx)
        return int(data) if data is not None else None

    def _on_history_source_toggled(self, checked: bool) -> None:
        self.history_scan_combo.setEnabled(
            checked and self.history_scan_combo.count() > 0
        )

    def _sync_history_export_option(self) -> None:
        watch_only = self.src_watch.isChecked()
        self.fmt_excel_history.setEnabled(watch_only)
        if watch_only:
            self.fmt_excel.setChecked(False)
            self.fmt_excel_history.setChecked(True)
        else:
            self.fmt_excel_history.setChecked(False)
            self.fmt_excel.setChecked(True)
            self.fmt_json.setChecked(True)

    def _on_browse(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Choose output folder", self.outdir_input.text(),
        )
        if d:
            self.outdir_input.setText(d)

    def formats(self) -> list[str]:
        out: list[str] = []
        for key, checkbox in (
            ("excel", self.fmt_excel),
            ("excel_history", self.fmt_excel_history),
            ("json", self.fmt_json),
            ("xml", self.fmt_xml),
        ):
            if checkbox.isChecked():
                out.append(key)
        return out

    def outdir(self) -> Path:
        return Path(self.outdir_input.text())

    def sources(self) -> dict:
        return {
            "tree": self.src_tree.isChecked(),
            "watch": self.src_watch.isChecked(),
            "history": self.src_history.isChecked(),
        }

    def template(self) -> str:
        return self.template_input.text()


# -- History tab ----------------------------------------------------------


class HistoryTab(QWidget):
    """List past scans for the connected PLC."""

    scans_changed = Signal(list)
    rescan_requested = Signal()

    _COL_WHEN = 0
    _COL_COUNT = 1
    _COL_NOTES = 2
    _COL_COMPARE = 3

    def __init__(self, db: DatabaseManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = db
        self._plc_id: Optional[int] = None
        self._loading = False
        self._compare_cells: list[CenteredCheckBoxCell] = []
        self._compare_order: list[int] = []
        self._compare_silent = False

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["When (Central)", "Tag count", "Notes", "Compare"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(self._COL_WHEN, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self._COL_COUNT, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self._COL_NOTES, QHeaderView.Stretch)
        h.setSectionResizeMode(self._COL_COMPARE, QHeaderView.Fixed)
        self.table.setColumnWidth(self._COL_COMPARE, 72)
        self.table.itemChanged.connect(self._on_item_changed)

        self.rescan_btn = QPushButton("Re-scan PLC")
        self.rescan_btn.setToolTip(
            "Run a new tag discovery on the connected PLC and save it to history"
        )
        self.rescan_btn.clicked.connect(self._on_rescan)
        browse_btn = QPushButton("Browse tags…")
        browse_btn.clicked.connect(self._on_browse)
        export_btn = QPushButton("Export selected scan…")
        export_btn.clicked.connect(self._on_export_selected)
        self.compare_btn = QPushButton("Compare checked scans")
        self.compare_btn.setToolTip(
            "Check exactly two scans in the Compare column, then click Compare"
        )
        self.compare_btn.clicked.connect(self._on_compare)
        self.compare_btn.setEnabled(False)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.rescan_btn)
        btn_row.addStretch()
        btn_row.addWidget(browse_btn)
        btn_row.addWidget(export_btn)
        btn_row.addWidget(self.compare_btn)

        hint = QLabel(
            "Check two scans in the Compare column to compare tag lists. "
            "Double-click Notes to add operator comments. Times are Central."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)

        self.status_label = QLabel("")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(hint)
        outer.addWidget(self.table)
        outer.addLayout(btn_row)
        outer.addWidget(self.status_label)

    def set_plc(self, plc: PlcConnection) -> None:
        if plc is None:
            self._plc_id = None
            self.table.setRowCount(0)
            return
        # Find the plc row id.
        all_plcs = self.db.list_plcs()
        for p in all_plcs:
            if p.ip == plc.ip and p.slot == plc.slot:
                # We need the id, but list_plcs doesn't return it.
                # Workaround: look up by inserting a temp marker.
                # Simpler: use the upsert to ensure a row exists, then
                # query by ip+slot to get the id.
                self._plc_id = self.db.upsert_plc(p)
                break
        self.refresh()

    def refresh(self) -> None:
        if self._plc_id is None:
            self.table.setRowCount(0)
            self.status_label.setText("Connect to a PLC to see its scan history.")
            self.scans_changed.emit([])
            return
        scans = self.db.list_scans(self._plc_id, limit=500)
        self._loading = True
        self._compare_cells.clear()
        self._compare_order.clear()
        self.table.blockSignals(True)
        self.table.setRowCount(len(scans))
        for r, s in enumerate(scans):
            when = QTableWidgetItem(format_scan_timestamp(s["scan_timestamp"]))
            when.setData(Qt.UserRole, s["id"])
            when.setData(Qt.UserRole + 1, s["scan_timestamp"])
            when.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(r, self._COL_WHEN, when)
            count_item = QTableWidgetItem(str(s["tag_count"]))
            count_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(r, self._COL_COUNT, count_item)
            notes_item = QTableWidgetItem(s.get("notes") or "")
            notes_item.setFlags(
                Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable
            )
            self.table.setItem(r, self._COL_NOTES, notes_item)
            cmp_cell = CenteredCheckBoxCell()
            cmp_cell.toggled.connect(
                lambda checked, r=r: self._on_compare_toggled(r, checked)
            )
            self._compare_cells.append(cmp_cell)
            self.table.setCellWidget(r, self._COL_COMPARE, cmp_cell)
        self.table.blockSignals(False)
        self._loading = False
        self.status_label.setText(
            f"{len(scans)} scan(s) on record for this PLC."
        )
        self.scans_changed.emit(scans)
        self._update_compare_button()

    def list_scans(self) -> list[dict]:
        if self._plc_id is None:
            return []
        return self.db.list_scans(self._plc_id, limit=500)

    def _scan_id_at_row(self, row: int) -> Optional[int]:
        item = self.table.item(row, self._COL_WHEN)
        if item is None:
            return None
        data = item.data(Qt.UserRole)
        return int(data) if data is not None else None

    def selected_scan_id(self) -> Optional[int]:
        """Return the ID of the selected scan row, or None."""
        rows = self.table.selectionModel().selectedRows()
        if rows:
            return self._scan_id_at_row(rows[0].row())
        return None

    def _checked_rows(self) -> list[int]:
        return [
            r for r, cell in enumerate(self._compare_cells)
            if cell.is_checked()
        ]

    def _set_compare_checked(self, row: int, checked: bool) -> None:
        if row < 0 or row >= len(self._compare_cells):
            return
        self._compare_silent = True
        try:
            self._compare_cells[row].set_checked(checked)
        finally:
            self._compare_silent = False

    def _sync_compare_state(self) -> None:
        """Drop unchecked rows from order; enable Compare when exactly two."""
        self._compare_order = [
            r for r in self._compare_order
            if 0 <= r < len(self._compare_cells)
            and self._compare_cells[r].is_checked()
        ]
        self.compare_btn.setEnabled(len(self._compare_order) == 2)

    def _on_compare_toggled(self, row: int, checked: bool) -> None:
        if self._loading or self._compare_silent:
            return
        if checked:
            if row in self._compare_order:
                self._compare_order.remove(row)
            self._compare_order.append(row)
            while len(self._compare_order) > 2:
                drop = self._compare_order.pop(0)
                self._set_compare_checked(drop, False)
                if drop in self._compare_order:
                    self._compare_order.remove(drop)
        elif row in self._compare_order:
            self._compare_order.remove(row)
        self._sync_compare_state()

    def _update_compare_button(self, *_args) -> None:
        if self._loading:
            return
        self._sync_compare_state()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or item.column() != self._COL_NOTES:
            return
        scan_id = self._scan_id_at_row(item.row())
        if scan_id is None:
            return
        try:
            self.db.update_scan_notes(scan_id, item.text())
        except Exception as e:
            QMessageBox.warning(self, "Notes not saved", str(e))

    def _on_rescan(self) -> None:
        if self._plc_id is None:
            QMessageBox.information(
                self, "Not connected",
                "Connect to a PLC before running a re-scan.",
            )
            return
        confirm = QMessageBox.question(
            self,
            "Re-scan PLC?",
            "Run a new tag discovery on the connected PLC?\n\n"
            "This saves a new entry in scan history. The watch list is kept.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.rescan_requested.emit()

    def _on_browse(self) -> None:
        rows = self.table.selectionModel().selectedRows()[:1]
        if not rows:
            QMessageBox.information(
                self, "No scan selected",
                "Select one scan row to browse its tag tree.",
            )
            return
        row = rows[0].row()
        scan_id = self._scan_id_at_row(row)
        raw_ts = self.table.item(row, self._COL_WHEN).data(Qt.UserRole + 1)
        label = format_scan_timestamp(str(raw_ts or ""))
        tree = self.db.load_scan(scan_id)
        if tree is None:
            QMessageBox.warning(self, "Load failed", "Could not load that scan.")
            return
        values = self.db.load_scan_values(scan_id)
        ScanBrowseDialog(
            tree, scan_label=label, values=values, parent=self,
        ).exec()

    def _on_compare(self) -> None:
        if len(self._compare_order) != 2:
            QMessageBox.information(
                self, "Check two scans",
                "Check exactly two scans in the Compare column, "
                "then click Compare checked scans.",
            )
            return
        row_a, row_b = self._compare_order[0], self._compare_order[1]
        id_a = self._scan_id_at_row(row_a)
        id_b = self._scan_id_at_row(row_b)
        label_a = self.table.item(row_a, self._COL_WHEN).data(Qt.UserRole + 1)
        label_b = self.table.item(row_b, self._COL_WHEN).data(Qt.UserRole + 1)
        label_a = str(label_a or "")
        label_b = str(label_b or "")
        try:
            ScanCompareDialog(
                self.db, id_a, id_b, label_a, label_b, parent=self,
            ).exec()
        except ValueError as e:
            QMessageBox.warning(self, "Compare failed", str(e))

    def _on_export_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        scan_id = self._scan_id_at_row(rows[0].row())
        tree = self.db.load_scan(scan_id)
        if tree is None:
            QMessageBox.warning(self, "Load failed", "Could not load that scan.")
            return
        d = QFileDialog.getSaveFileName(
            self, "Save snapshot as JSON",
            str(self.db.path) and str(Path(self.db.path).parent / f"scan_{scan_id}.json"),
            "JSON (*.json)",
        )
        if not d[0]:
            return
        out = Path(d[0])
        try:
            import plck.export as _exp
            _exp.export_tags(tree, fmt="json", out_dir=out.parent, base_name=out.name)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", f"{e}")
            return
        self.status_label.setText(f"Wrote {out}")


# -- Diagnostics tab ------------------------------------------------------


class DiagnosticsTab(QWidget):
    """Connection summary + read history log + clear log button."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._events: deque = deque(maxlen=500)

        # Connection summary
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.summary_text.setFrameShape(QFrame.StyledPanel)
        summary_box = QFrame()
        sl = QVBoxLayout(summary_box)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(4)
        sl.addWidget(QLabel("<b>Connection summary</b>"))
        sl.addWidget(self.summary_text)

        # Read log
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_box = QFrame()
        ll = QVBoxLayout(log_box)
        ll.addWidget(QLabel("<b>Read history</b> (most recent first)"))
        ll.addWidget(self.log_text)

        # Clear button + counts
        self.reads_label = QLabel("0 reads · 0 errors")
        clear_btn = QPushButton("Clear log")
        clear_btn.clicked.connect(self._on_clear)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.reads_label)
        btn_row.addStretch()
        btn_row.addWidget(clear_btn)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(summary_box)
        outer.addWidget(log_box)
        outer.addLayout(btn_row)

    def set_connection(self, plc: PlcConnection) -> None:
        if plc is None:
            self.summary_text.setPlainText("(not connected)")
            return
        d = plc
        txt = (
            f"Nickname:  {d.display_label()}\n"
            f"Device ID: {d.device_label() or '?'}\n"
            f"IP:        {d.ip}\n"
            f"Slot:      {d.slot}\n"
            f"Port:      {d.port}\n"
            f"CIP path:  {d.cip_path or '(slot only)'}\n"
            f"Product:   {d.product_name or '?'}\n"
            f"Revision:  {d.revision or '?'}\n"
            f"Vendor:    {d.vendor or '?'}\n"
            f"Serial:    {d.serial_number or '?'}\n"
            f"Driver:    pylogix.PLC\n"
            f"Driver version: pylogix {_PYLOGIX_VERSION}\n"
            f"Mode:      READ-ONLY (no writes to the PLC)\n"
        )
        self.summary_text.setPlainText(txt)
        fm = self.summary_text.fontMetrics()
        line_count = txt.count("\n") + 1
        self.summary_text.setFixedHeight(fm.lineSpacing() * line_count + 16)

    def log_event(self, event: str) -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}]  {event}"
        self._events.appendleft(line)
        # Re-render (cheaper than appending to QTextEdit one line at a time).
        self.log_text.setPlainText("\n".join(self._events))

    def log_reads(self, results: list[ReadResult]) -> None:
        n_total = len(results)
        n_err = sum(1 for r in results if r.quality.value != "Good")
        self.reads_label.setText(
            f"{n_total} tag(s) this cycle · {n_err} error(s) this cycle"
        )
        # Log each error in detail.
        for r in results:
            if r.quality.value != "Good":
                self.log_event(
                    f"READ ERROR  {r.tag_name}  {r.error}  ({r.elapsed_ms:.0f}ms)"
                )

    def _on_clear(self) -> None:
        if not self._events:
            return
        confirm = QMessageBox.question(
            self, "Clear log?",
            "Clear the in-memory read history?\n\n"
            "The on-disk session log (if any) is not affected.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self._events.clear()
        self.log_text.clear()
        self.reads_label.setText("0 reads · 0 errors")


# -- WorkspaceView: top-level container ----------------------------------


class WorkspaceView(QWidget):
    """The 5-tab workspace, the 'inside-the-PLC' view."""

    disconnected = Signal()  # user clicked Disconnect

    def __init__(
        self,
        db: DatabaseManager,
        outdir: Path,
        settings: Optional[AppSettings] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.outdir = outdir
        self.settings = settings or AppSettings.load()
        self._plc: Optional[PlcConnection] = None
        self._tree: Optional[TagTree] = None
        self._last_scan_id: Optional[int] = None
        self._scan_source = "manual"
        self._discovery_worker: Optional[DiscoveryWorker] = None
        self._discovery_dialog: Optional[QProgressDialog] = None
        self._export_worker: Optional[ExportWorker] = None
        self._export_dialog: Optional[QProgressDialog] = None
        self._monitor_worker: Optional[MonitorWorker] = None
        self._connected = False
        self._connection_epoch = 0
        self._started_at: Optional[float] = None
        self._reads_per_sec: float = 0.0
        self._read_errors: int = 0

        # -- Header (back-link + title + disconnect) ---------------------
        self.back_btn = QPushButton("← Connections")
        self.back_btn.clicked.connect(self._on_back)
        self.title_label = QLabel("Workspace — (not connected)")
        self.title_label.setObjectName("workspaceTitle")
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self._on_disconnect)
        self.disconnect_btn.setObjectName("destructiveBtn")

        self.readonly_banner = QLabel(
            "READ-ONLY — no writes to the PLC"
        )
        self.readonly_banner.setObjectName("readonlyBanner")
        self.readonly_banner.setStyleSheet(
            "QLabel#readonlyBanner { background: #3A2E1F; color: #B8860B; "
            "padding: 4px 10px; border: 1px solid #B8860B; border-radius: 3px; }"
        )

        # -- Tabs -------------------------------------------------------
        self.tabs = QTabWidget()
        self.browse_tab = BrowseTab()
        self.monitor_tab = MonitorTab(
            history_samples=self.settings.trend_window_samples,
        )
        self.export_tab = ExportTab(outdir)
        self.history_tab = HistoryTab(db)
        self.diagnostics_tab = DiagnosticsTab()
        self.tabs.addTab(self.browse_tab, "Browse")
        self.tabs.addTab(self.monitor_tab, "Monitor")
        self.tabs.addTab(self.export_tab, "Export")
        self.tabs.addTab(self.history_tab, "Tag History")
        self.tabs.addTab(self.diagnostics_tab, "Diagnostics")

        # -- Connect monitor signals ----------------------------------
        self.monitor_tab.add_requested.connect(
            lambda tag: self._on_watchlist_changed()
        )
        self.monitor_tab.remove_requested.connect(
            lambda tag: (self._on_watchlist_changed(), self.browse_tab.mark_as_not_monitored(tag))
        )
        self.monitor_tab.cleared.connect(self._on_watchlist_changed)

        self.browse_tab.add_to_monitor_requested.connect(self._on_add_to_monitor)
        self.browse_tab.navigate_to_monitor_requested.connect(
            self._on_add_to_monitor_and_navigate
        )
        self.browse_tab.remove_from_monitor_requested.connect(
            self._on_remove_from_monitor
        )
        self.browse_tab.scan_values_ready.connect(self._on_scan_values_saved)
        self.history_tab.scans_changed.connect(self.export_tab.set_history_scans)
        self.history_tab.rescan_requested.connect(self.trigger_rescan)

        self.export_tab.run_btn.clicked.connect(self._on_export)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusBar")

        # -- Top bar (brand + navigation) --------------------------------
        topbar = QHBoxLayout()
        topbar.addWidget(BrandHeader(), 1)

        nav = QHBoxLayout()
        nav.addWidget(self.back_btn)
        nav.addSpacing(12)
        nav.addWidget(self.title_label, 1)
        nav.addWidget(self.disconnect_btn)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.addLayout(topbar)
        outer.addLayout(nav)
        outer.addWidget(self.readonly_banner)
        outer.addWidget(self.tabs, 1)
        outer.addWidget(self.status_label)

        self.export_tab.set_filename_template(self.settings.filename_template)
        self._apply_poll_default()

    def apply_settings(self, settings: AppSettings) -> None:
        self.settings = settings
        self.outdir = settings.resolved_export_dir()
        self.export_tab.set_default_outdir(self.outdir)
        self.export_tab.set_filename_template(settings.filename_template)
        self.monitor_tab.set_history_samples(settings.trend_window_samples)
        self._apply_poll_default()

    def _apply_poll_default(self) -> None:
        rate = int(self.settings.default_poll_rate_s)
        label = {5: "5 s", 15: "15 s", 30: "30 s", 60: "1 min", 300: "5 min"}.get(
            rate, "5 s"
        )
        idx = self.monitor_tab.interval_combo.findText(label)
        if idx >= 0:
            self.monitor_tab.interval_combo.setCurrentIndex(idx)

    def _on_tab_changed(self, index: int) -> None:
        if self._plc is None:
            return
        names = ["Browse", "Monitor", "Export", "History", "Diagnostics"]
        tab = names[index] if 0 <= index < len(names) else "?"
        if tab == "Export":
            self.status_label.setText(
                f"Export tab — output folder: {self.export_tab.outdir()}"
            )
        elif tab == "History":
            self.status_label.setText(
                "History — check two scans to compare; double-click Notes to edit."
            )
        elif tab == "Diagnostics":
            self.status_label.setText(
                f"Diagnostics — pylogix {_PYLOGIX_VERSION} · connection log below."
            )
        elif tab == "Monitor":
            n = len(self.monitor_tab.watch_list())
            self.status_label.setText(
                f"Monitor — {n} tag(s) · check Chart column · "
                f"poll every {self.monitor_tab.interval_seconds():.0f}s"
            )
        elif self._tree is not None:
            self.status_label.setText(
                f"Browse — {self._tree.count()} tags · connected to {self._plc.ip}"
            )

    # -- Public API -------------------------------------------------------

    def trigger_rescan(self) -> None:
        """Re-run tag discovery on the connected PLC (keeps watch list)."""
        if self._plc is None:
            return
        if self._discovery_worker is not None and self._discovery_worker.isRunning():
            QMessageBox.information(
                self, "Scan in progress",
                "Discovery is already running — wait for it to finish.",
            )
            return
        self._scan_source = "re-discover"
        self._run_discovery(
            self._plc,
            banner=f"Re-scanning tags on {self._plc.ip} (slot {self._plc.slot})…",
        )

    def _run_discovery(self, plc: PlcConnection, banner: str = "") -> None:
        self._stop_discovery_worker()
        self.browse_tab.set_discovery_active(True, banner or f"Connecting to {plc.ip}…")
        self._show_discovery_dialog(
            banner or f"Connecting to {plc.ip} (slot {plc.slot})…"
        )
        worker = DiscoveryWorker(
            plc, timeout_s=self.settings.connection_timeout_s
        )
        epoch = self._connection_epoch
        worker.signals.started.connect(
            lambda e=epoch: self._on_discovery_started(e, banner, plc.ip)
        )
        worker.signals.progress.connect(
            lambda msg, e=epoch: self._on_discovery_progress_guarded(msg, e)
        )
        worker.signals.finished.connect(
            lambda tree, e=epoch: self._on_discovery_finished_guarded(tree, e)
        )
        worker.signals.failed.connect(
            lambda msg, e=epoch: self._on_discovery_failed_guarded(msg, e)
        )
        worker.signals.unsupported.connect(
            lambda plc_obj, e=epoch: self._on_discovery_unsupported_guarded(plc_obj, e)
        )
        worker.start()
        self._discovery_worker = worker
        self.diagnostics_tab.log_event(
            f"DISCOVERY started on {plc.ip} slot {plc.slot} ({self._scan_source})"
        )

    def _on_discovery_started(
        self, epoch: int, banner: str, ip: str,
    ) -> None:
        if not self._connected or epoch != self._connection_epoch:
            return
        self.status_label.setText("Connecting…")
        self.browse_tab.update_discovery_progress(
            banner or f"Connecting to {ip}…"
        )

    def connect_to(self, plc: PlcConnection) -> None:
        """Start a discovery on a worker thread. When the tree comes back,
        populate the browse tab and start the monitor worker (if any
        tags are in the watch list).
        """
        self._stop_workers()
        self._connection_epoch += 1
        self._connected = True

        self.title_label.setText(
            f"Workspace — {plc.display_label()} ({plc.ip}, slot {plc.slot})"
        )
        self.history_tab.set_plc(plc)
        self.diagnostics_tab.set_connection(plc)
        self.status_label.setText(f"Connecting to {plc.ip}…")

        # Workers construct their own PLCClient inside their thread. Do not
        # create a PLCClient on the UI thread and pass it across threads.
        self._plc = plc
        self.browse_tab.set_plc(plc)
        self.browse_tab.set_discovery_active(
            True, f"Connecting to {plc.ip} (slot {plc.slot})…"
        )
        self._started_at = time.monotonic()
        self._scan_source = "manual"
        self.tabs.setCurrentWidget(self.browse_tab)
        self._run_discovery(
            plc,
            banner=f"Connecting to {plc.ip} (slot {plc.slot})…",
        )

    def shutdown(self) -> None:
        """Stop everything. Called on app exit or when switching PLCs."""
        self._stop_workers()
        self.browse_tab.shutdown()

    # -- Internal --------------------------------------------------------

    def _on_back(self) -> None:
        confirm = QMessageBox.question(
            self, "Disconnect?",
            "Return to the Connection Manager?\n\n"
            "The live connection to this PLC will be closed. "
            "Monitor collected history is not saved — disconnecting clears the "
            "watch list and all trend samples. Export from the Export tab "
            "(Monitor watch list only → Excel w/ collected history) before "
            "leaving if you need the data.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self._stop_workers()
        self.disconnected.emit()

    def _on_disconnect(self) -> None:
        self._on_back()

    def _on_discovery_progress_guarded(self, msg: str, epoch: int) -> None:
        if not self._connected or epoch != self._connection_epoch:
            return
        self._on_discovery_progress(msg)

    def _on_discovery_finished_guarded(self, tree: TagTree, epoch: int) -> None:
        if not self._connected or epoch != self._connection_epoch:
            return
        if self._plc is None or tree.plc.ip != self._plc.ip:
            return
        self._on_discovery_finished(tree)

    def _on_discovery_failed_guarded(self, message: str, epoch: int) -> None:
        if not self._connected or epoch != self._connection_epoch:
            return
        self._on_discovery_failed(message)

    def _on_discovery_unsupported_guarded(
        self, plc_obj: PlcConnection, epoch: int
    ) -> None:
        if not self._connected or epoch != self._connection_epoch:
            return
        self._on_discovery_unsupported(plc_obj)

    def _on_discovery_unsupported(self, plc_obj: PlcConnection) -> None:
        """A direct/manual connection reached a non-Logix device. Show a
        clear 'not supported' message naming the device type, then return
        to the Connection Manager (we cannot browse this device)."""
        self._close_discovery_dialog()
        self.browse_tab.set_discovery_active(False)
        name = plc_obj.product_name or "Unknown device"
        self.status_label.setText(f"Unsupported device: {name}")
        self.diagnostics_tab.log_event(
            f"CONNECT blocked: unsupported device {name} at {plc_obj.ip}"
        )
        self._stop_workers()
        # An unsupported device must never live in the saved connections
        # list — only devices we can actually browse belong there. Remove
        # it if it was saved (e.g. added via "Save & connect").
        try:
            self.db.remove_plc(plc_obj.ip, plc_obj.slot)
        except Exception as e:
            self.diagnostics_tab.log_event(f"DB cleanup failed: {e}")
        QMessageBox.warning(
            self, "Device not supported",
            unsupported_device_message(plc_obj.product_name),
        )
        self.disconnected.emit()

    def _on_discovery_progress(self, msg: str) -> None:
        self.status_label.setText(msg)
        self.browse_tab.update_discovery_progress(msg)
        if self._discovery_dialog is not None:
            self._discovery_dialog.setLabelText(msg)

    def _on_discovery_finished(self, tree: TagTree) -> None:
        self._close_discovery_dialog()
        self._tree = tree
        self.browse_tab.load_tree(tree)
        # Refresh the Diagnostics summary with the live device info now that
        # get_device_info() has populated vendor / serial / product / revision
        # (these aren't persisted in the saved-connection row, so the initial
        # pre-discovery summary showed '?').
        self.diagnostics_tab.set_connection(tree.plc)
        n = tree.count()
        leaves = tree.leaf_count()
        elapsed = tree.discovery_duration_s
        self.status_label.setText(
            f"Discovered {n:,} nodes ({leaves:,} leaves) in {elapsed:.1f}s."
        )
        self.diagnostics_tab.log_event(
            f"DISCOVERY complete: {n:,} nodes, {leaves:,} leaves, {elapsed:.1f}s"
        )
        # Start the monitor worker.
        self._start_monitor()
        # Auto-fill tree value column with a one-shot batch read of all
        # leaf tags. Values appear gradually as each batch completes.
        leaf_paths = tree.leaf_names()
        if leaf_paths and self._plc is not None:
            self.browse_tab.populate_tree_values(self._plc, leaf_paths)
        # Persist the snapshot AFTER the tree has painted so connect feels
        # instant. Deferred to the next event-loop turn (small/fast now that
        # bits aren't serialized). Headless/test mode persists inline.
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            self._persist_snapshot(tree, self._connection_epoch)
        else:
            epoch = self._connection_epoch
            QTimer.singleShot(0, lambda: self._persist_snapshot(tree, epoch))

    def _persist_snapshot(self, tree: TagTree, epoch: int) -> None:
        if not self._connected or epoch != self._connection_epoch:
            return  # disconnected/reconnected before the deferred write ran
        try:
            plc_id = self.db.upsert_plc(tree.plc)
            self._last_scan_id = self.db.save_tag_snapshot(
                plc_id, tree, source=self._scan_source,
            )
            self._scan_source = "manual"
            self.history_tab.set_plc(tree.plc)
        except Exception as e:
            self.diagnostics_tab.log_event(f"DB write failed: {e}")
            self._last_scan_id = None

    def _on_scan_values_saved(self, values: dict) -> None:
        if not self._connected or self._plc is None:
            return
        if self._last_scan_id is None or not values:
            return
        try:
            self.db.save_scan_values(self._last_scan_id, values)
            self.diagnostics_tab.log_event(
                f"Saved {len(values)} tag value(s) with scan {self._last_scan_id}"
            )
        except Exception as e:
            self.diagnostics_tab.log_event(f"Scan values save failed: {e}")

    def _on_discovery_failed(self, message: str) -> None:
        self._close_discovery_dialog()
        self.browse_tab.set_discovery_active(False)
        self.status_label.setText(f"Discovery failed: {message}")
        self.diagnostics_tab.log_event(f"DISCOVERY failed: {message}")
        QMessageBox.critical(
            self, "Discovery failed",
            f"Could not discover tags: {message}",
        )

    # -- Discovery progress dialog --------------------------------------

    def _show_discovery_dialog(self, message: str) -> None:
        """Modal busy dialog so a 20–30s discovery is obviously working."""
        self._close_discovery_dialog()
        dlg = QProgressDialog(message, "Cancel", 0, 0, self)
        dlg.setWindowTitle("Discovering tags")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)        # show immediately
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setValue(0)                  # range (0,0) => indeterminate/busy bar
        dlg.canceled.connect(self._on_discovery_cancelled)
        self._discovery_dialog = dlg
        dlg.show()

    def _close_discovery_dialog(self) -> None:
        dlg = self._discovery_dialog
        if dlg is None:
            return
        self._discovery_dialog = None
        try:
            dlg.canceled.disconnect(self._on_discovery_cancelled)
        except (TypeError, RuntimeError):
            pass
        dlg.reset()
        dlg.deleteLater()

    def _on_discovery_cancelled(self) -> None:
        self._close_discovery_dialog()
        self.status_label.setText("Discovery cancelled.")
        self.diagnostics_tab.log_event("DISCOVERY cancelled by user")
        self._stop_workers()
        self.disconnected.emit()

    def _start_monitor(self) -> None:
        if self._plc is None:
            return
        # Don't start a monitor with no tags; the worker will idle.
        interval = self.monitor_tab.interval_seconds()
        worker = MonitorWorker(
            self._plc,
            self.monitor_tab.watch_list(),
            interval_s=interval,
        )
        worker.signals.started.connect(
            lambda: self.diagnostics_tab.log_event("MONITOR started")
        )
        worker.signals.sample.connect(self._on_monitor_sample)
        worker.signals.failed.connect(self._on_monitor_failed)
        worker.signals.stopped.connect(
            lambda: self.diagnostics_tab.log_event("MONITOR stopped")
        )
        worker.start()
        self._monitor_worker = worker

    def _on_monitor_sample(self, results: list[ReadResult]) -> None:
        if not self._connected or self._plc is None:
            return
        if self.monitor_tab.is_paused():
            return
        self.monitor_tab.apply_samples(results)
        self.diagnostics_tab.log_reads(results)

    def _on_monitor_failed(self, message: str) -> None:
        if not self._connected or self._plc is None:
            return
        self.diagnostics_tab.log_event(f"MONITOR error: {message}")
        self.status_label.setText(f"Monitor error: {message}")

    def _on_watchlist_changed(self) -> None:
        if self._monitor_worker is not None:
            self._monitor_worker.set_tags(self.monitor_tab.watch_list())

    def _on_add_to_monitor(self, tag: str) -> None:
        """Add a tag from the Browse tree's "+" button to the Monitor watch
        list WITHOUT navigating away. add_tag() emits add_requested, which is
        already wired to _on_watchlist_changed to push the new list to the
        running monitor worker."""
        dtype = self.browse_tab.tag_type(tag)
        if not self.monitor_tab.add_tag(tag, data_type=dtype):
            return
        self.browse_tab.mark_as_monitored(tag)

    def _on_add_to_monitor_and_navigate(self, tag: str) -> None:
        """Add a tag and switch to the Monitor tab — used by the inspector's
        'Add to monitor + go to tab' button."""
        dtype = self.browse_tab.tag_type(tag)
        if not self.monitor_tab.add_tag(tag, data_type=dtype):
            return
        self.browse_tab.mark_as_monitored(tag)
        self.tabs.setCurrentWidget(self.monitor_tab)

    def _on_remove_from_monitor(self, tag: str) -> None:
        """Remove a tag from the monitor via the tree's '−' button."""
        self.monitor_tab.remove_tag(tag)
        self.browse_tab.mark_as_not_monitored(tag)

    def _on_export(self) -> None:
        """Run the export pipeline from the Export tab."""
        formats = self.export_tab.formats()
        if not formats:
            QMessageBox.warning(self, "No formats selected",
                                "Select at least one export format.")
            return
        outdir = self.export_tab.outdir()
        tree_formats = [f for f in formats if f != "excel_history"]
        want_history = "excel_history" in formats
        fmt_list = ", ".join(formats)
        auto_confirm = os.environ.get("QT_QPA_PLATFORM") == "offscreen"
        if not auto_confirm:
            confirm = QMessageBox.question(
                self,
                "Export tags?",
                f"Write export file(s) ({fmt_list}) to:\n\n{outdir}\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return
        srcs = self.export_tab.sources()
        tree_source = srcs.get("tree", True)
        watch_source = srcs.get("watch", False)
        history_source = srcs.get("history", False)
        template = self.export_tab.template()

        pre_errors: list[str] = []
        history_payload = None
        nickname = self._plc.nickname if self._plc is not None else "plc"

        # Resolve the monitor-history job (validated on the UI thread).
        if want_history:
            if not watch_source:
                pre_errors.append(
                    "excel_history: select Monitor watch list only as the source"
                )
            elif not self.monitor_tab.watch_list():
                pre_errors.append("excel_history: watch list is empty")
            else:
                history_payload = self.monitor_tab.history_export_payload()

        # Resolve the tag-tree job (load saved scan or use the live/synth tree).
        export_tree = None
        if tree_formats:
            if history_source:
                scan_id = self.export_tab.selected_history_scan_id()
                if scan_id is None:
                    QMessageBox.warning(
                        self, "No scan selected",
                        "Choose a saved scan from the dropdown on the Export tab.",
                    )
                    return
                export_tree = self.db.load_scan(scan_id)
                if export_tree is None:
                    QMessageBox.warning(
                        self, "Load failed",
                        f"Could not load scan {scan_id} from the database.",
                    )
                    return
            else:
                if self._tree is None:
                    QMessageBox.warning(
                        self, "Nothing to export",
                        "Connect to a PLC and run discovery first, or export a "
                        "saved scan from the dropdown.",
                    )
                    return
                export_tree = (
                    self._synthesize_watch_tree() if watch_source else self._tree
                )

        if export_tree is None and history_payload is None and not pre_errors:
            QMessageBox.warning(
                self, "Nothing exported",
                "No files were written. Check source and format selections.",
            )
            return

        worker = ExportWorker(
            out_dir=outdir,
            filename_template=template,
            tree=export_tree,
            tree_formats=tree_formats,
            history_payload=history_payload,
            history_plc=self._plc,
            history_nickname=nickname,
            pre_errors=pre_errors,
        )

        if auto_confirm:
            # Test / headless mode: run synchronously so results are immediate.
            written, errors = worker.execute()
            self._finish_export_status(written, errors)
            return

        # Threaded export with an "Exporting…" busy popup so the UI never
        # freezes while files are written.
        self._show_export_dialog()
        self._export_worker = worker
        worker.signals.progress.connect(self._on_export_progress)
        worker.signals.finished.connect(self._on_export_finished)
        worker.start()

    def _show_export_dialog(self) -> None:
        self._close_export_dialog()
        dlg = QProgressDialog("Exporting…", None, 0, 0, self)
        dlg.setWindowTitle("Exporting")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setCancelButton(None)  # writes can't be safely aborted mid-file
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setValue(0)
        self._export_dialog = dlg
        dlg.show()

    def _close_export_dialog(self) -> None:
        dlg = getattr(self, "_export_dialog", None)
        if dlg is None:
            return
        self._export_dialog = None
        dlg.reset()
        dlg.deleteLater()

    def _on_export_progress(self, msg: str) -> None:
        dlg = getattr(self, "_export_dialog", None)
        if dlg is not None:
            dlg.setLabelText(msg)

    def _on_export_finished(self, written: list, errors: list) -> None:
        self._close_export_dialog()
        self._export_worker = None
        self._finish_export_status(written, errors)

    def _finish_export_status(
        self, written: list[Path], errors: list[str],
    ) -> None:
        if written:
            self.export_tab.status_label.setText(
                "Exported: " + ", ".join(str(f) for f in written)
            )
        if errors:
            msg = " | Errors: " + "; ".join(errors)
            prev = self.export_tab.status_label.text()
            self.export_tab.status_label.setText(prev + msg if prev else msg.strip())

    def _stop_discovery_worker(self, wait_ms: int = 10000) -> None:
        self._close_discovery_dialog()
        worker = self._discovery_worker
        if worker is None:
            return
        self._discovery_worker = None
        disconnect_worker_signals(worker)
        worker.stop()
        if worker.isRunning():
            worker.wait(wait_ms)

    def _disconnect_worker_signals(self, worker) -> None:
        """Prevent late worker signals from touching UI after disconnect."""
        disconnect_worker_signals(worker)

    def _stop_workers(self) -> None:
        self._connected = False
        self._connection_epoch += 1

        if self._export_worker is not None:
            worker = self._export_worker
            self._export_worker = None
            self._disconnect_worker_signals(worker)
            if worker.isRunning():
                worker.wait(10000)
            self._close_export_dialog()

        if self._monitor_worker is not None:
            worker = self._monitor_worker
            self._monitor_worker = None
            self._disconnect_worker_signals(worker)
            worker.stop()
            if worker.isRunning():
                worker.wait(5000)

        self._stop_discovery_worker()

        self.browse_tab.stop_background_workers()
        self.browse_tab.set_discovery_active(False)
        self.browse_tab.reset_inspector()
        self.monitor_tab.clear_silent()
        self._plc = None
        self.browse_tab.set_plc(None)
        self._tree = None
        self.status_label.setText("")
        self.title_label.setText("Workspace — (not connected)")

    # -- Export runner (called from the Export tab) ----------------------

    def run_export(
        self,
        formats: list[str],
        outdir: Path,
        watch_list_source: bool,
        tree_source: bool,
    ) -> list[Path]:
        """Run the export pipeline. Returns the list of files written.

        Source selection: if watch_list_source and the monitor watch list
        is non-empty, export a flat list of those tags (one synthesized
        tree). Else if tree_source and we have a discovery tree, export
        the whole tree. Else, raise.
        """
        from plck.export import export_tags
        out = []
        if watch_list_source and self.monitor_tab.watch_list():
            tree = self._synthesize_watch_tree()
        elif tree_source and self._tree is not None:
            tree = self._tree
        elif self._tree is not None:
            tree = self._tree
        else:
            raise RuntimeError("No tag tree to export. Run discovery first.")
        for fmt in formats:
            written = export_tags(tree, fmt=fmt, out_dir=outdir)
            out.extend(written)
        return out

    def _synthesize_watch_tree(self) -> TagTree:
        """Build a flat TagTree containing just the watch list tags.

        Used for the "Export → Watch list" path. Each watch-list tag
        becomes a top-level leaf; their full UDT membership is NOT
        included (the GUI does the read; we export the names).
        """
        assert self._tree is not None
        nodes = []
        for name in self.monitor_tab.watch_list():
            found = self._tree.find(name)
            if found is not None:
                nodes.append(found)
            else:
                # Synthesize a placeholder so the export still works.
                nodes.append(TagNode(name=name, data_type=TagDataType.OTHER))
        return TagTree(
            plc=self._tree.plc,
            root=nodes,
            discovered_at=self._tree.discovered_at,
        )
