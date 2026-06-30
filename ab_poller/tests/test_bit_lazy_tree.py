"""Browse tree creates integer bit children lazily (on expand).

Materializing every word's 8–64 BOOL bits up front froze search/filter on
bit-heavy controllers. Bits must be created only when the word is expanded.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from plc_toolkit.ui.workspace_view import BrowseTab
from plck.models import PlcConnection, TagDataType, TagNode, TagTree


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _dint_with_bits(name: str) -> TagNode:
    node = TagNode(name=name, data_type=TagDataType.DINT)
    node.members = [
        TagNode(name=f"{name}.{i}", data_type=TagDataType.BOOL, bit_index=i)
        for i in range(32)
    ]
    return node


def _tree() -> TagTree:
    return TagTree(
        plc=PlcConnection(nickname="T", ip="192.0.2.10"),
        root=[_dint_with_bits("Well_1.WELL_ALARM_WORD")],
        discovered_at="2026-06-17T00:00:00Z",
    )


def test_bit_children_are_lazy_until_expanded(qapp):
    tab = BrowseTab()
    tab.load_tree(_tree())

    word = tab.tree.topLevelItem(0)
    # Not materialized yet — no 32 child items sitting in the widget.
    assert word.childCount() == 0

    # Simulate the operator expanding the word.
    word.setExpanded(True)
    assert word.childCount() == 32
    assert word.child(0).text(tab._COL_TAG) == "0"
    assert word.child(31).text(tab._COL_TAG) == "31"

    # Re-expanding does not duplicate children.
    word.setExpanded(False)
    word.setExpanded(True)
    assert word.childCount() == 32


def test_expanded_bits_derive_values_from_word(qapp):
    tab = BrowseTab()
    tab.load_tree(_tree())
    word = tab.tree.topLevelItem(0)

    # Word value arrives (bit 1 and bit 3 set => 0b1010 = 10).
    tab._update_tree_value("Well_1.WELL_ALARM_WORD", 10)
    word.setExpanded(True)
    bits = [word.child(i).text(tab._COL_VALUE) for i in range(4)]
    assert bits == ["0", "1", "0", "1"]
