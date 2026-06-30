from __future__ import annotations

import pytest

from plck.discovery import _build_node
from plck.models import TagDataType


@pytest.mark.parametrize(
    "type_name,expected,bit_width",
    [
        ("USINT", TagDataType.USINT, 8),
        ("UINT", TagDataType.UINT, 16),
        ("UDINT", TagDataType.UDINT, 32),
        ("ULINT", TagDataType.ULINT, 64),
        ("TIME", TagDataType.TIME, 0),  # not bit-addressable
    ],
)
def test_build_node_accepts_pylogix_atomic_types(type_name, expected, bit_width):
    node = _build_node(f"Tag_{type_name}", type_name, {}, max_depth=8, depth=0)

    assert node.data_type == expected
    assert len(node.members) == bit_width
    if bit_width:
        assert node.is_bit_word()
        assert [m.bit_index for m in node.members] == list(range(bit_width))
        assert all(m.data_type == TagDataType.BOOL for m in node.members)
        assert node.members[0].name == f"Tag_{type_name}.0"
    else:
        assert not node.members


def test_build_node_preserves_array_dimensions_for_atomic_types():
    # Arrays of integer types are NOT bit-expanded (would multiply the tree
    # by 8–64x per element).
    node = _build_node("ArrayTag", "UINT[10]", {}, max_depth=8, depth=0)

    assert node.data_type == TagDataType.UINT
    assert node.is_array is True
    assert node.array_dim == [10]
    assert not node.members
