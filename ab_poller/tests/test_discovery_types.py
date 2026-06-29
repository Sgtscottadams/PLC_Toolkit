from __future__ import annotations

import pytest

from plck.discovery import _build_node
from plck.models import TagDataType


@pytest.mark.parametrize(
    "type_name,expected",
    [
        ("USINT", TagDataType.USINT),
        ("UINT", TagDataType.UINT),
        ("UDINT", TagDataType.UDINT),
        ("ULINT", TagDataType.ULINT),
        ("TIME", TagDataType.TIME),
    ],
)
def test_build_node_accepts_pylogix_atomic_types(type_name, expected):
    node = _build_node(f"Tag_{type_name}", type_name, {}, max_depth=8, depth=0)

    assert node.data_type == expected
    assert not node.members


def test_build_node_preserves_array_dimensions_for_atomic_types():
    node = _build_node("ArrayTag", "UINT[10]", {}, max_depth=8, depth=0)

    assert node.data_type == TagDataType.UINT
    assert node.is_array is True
    assert node.array_dim == [10]
