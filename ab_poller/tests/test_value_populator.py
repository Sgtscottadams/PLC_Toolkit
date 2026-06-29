"""Browse value populator thread lifecycle."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from plck.models import PlcConnection
from plc_toolkit.ui.workspace_view import BrowseTab
from plc_toolkit.workers import TreeValuePopulator


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_value_populator_set_tags_resets_position():
    pop = TreeValuePopulator(
        PlcConnection(nickname="T", ip="192.0.2.1"),
        ["A", "B", "C"],
    )
    pop._pos = 50
    pop.set_tags(["X", "Y"])
    assert pop.tags == ["X", "Y"]
    assert pop._pos == 0


def test_start_value_populator_reuses_running_thread(qapp):
    """Reprioritize while running must not replace the QThread object."""
    tab = BrowseTab()
    tab._plc = PlcConnection(nickname="T", ip="192.0.2.1")
    tab._all_leaf_tags = ["T1", "T2", "T3"]
    tab._values_loaded = set()

    class FakePop:
        def __init__(self):
            self.tags = []

        def isRunning(self):
            return True

        def set_tags(self, tags):
            self.tags = list(tags)

    fake = FakePop()
    tab._value_populator = fake
    tab._populator_order = ["T1", "T2", "T3"]

    tab._start_value_populator(["T2", "T1", "T3"])
    assert tab._value_populator is fake
    assert fake.tags == ["T2", "T1", "T3"]
