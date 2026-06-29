"""Shared tag-tree display helpers."""

from __future__ import annotations

from plck.models import TagNode


def format_type_label(node: TagNode) -> str:
    """Format the Type column — UDT/struct parents show member count."""
    if node.members:
        return f"{node.data_type.value} ({len(node.members)})"
    return node.data_type.value
