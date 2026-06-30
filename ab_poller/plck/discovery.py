"""plck.discovery — Build a TagTree from a connected PLC.

This is the work the migration analysis flagged as the one non-trivial
piece: pylogix has no per-tag UDT accessor (open issue #125 since
2020-04-20). We walk `client._client.UDTByName` ourselves to build the
nested tree.

Algorithm:
    1. Call GetTagList(allTags=True). This populates both the top-level
       Tag list AND pylogix's internal UDT cache (plc.UDT / UDTByName).
    2. For each top-level Tag:
         - If DataType is a UDT name: create a UDT parent node, recurse
           into UDTByName[DataType].Fields to build members.
         - Else: create an atomic leaf node.
    3. For each program (pylogix's GetProgramsList), call
       GetProgramTagList and append tags under a virtual "Program:..."
       parent.
    4. Mark AB-module I/O tags (RIO:I, RIO:O, RIO:x:C) as read-only —
       their `.C` config tags are write-locked when the controller is
       in Run mode, but the `:I`/`:O` data tags are read-only by
       design. We tag the data tags as not-writeable and the config
       tags as writeable-but-locked.

Caching: pylogix's UDTByName is a per-PLC instance cache. We don't add
our own cache layer — the discovery operation is heavy and an
operator-triggered re-discover is the right time to invalidate.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from plck.comms import PLCClient
from plck.errors import PlcError
from plck.models import TagDataType, TagNode, TagTree

# A small set of pylogix types that we recognize as atomic. Anything
# not on this list is treated as a UDT (looked up in UDTByName) or
# falls back to TagDataType.OTHER.
_ATOMIC_TYPES = {
    "BOOL", "SINT", "INT", "DINT", "LINT",
    "USINT", "UINT", "UDINT", "ULINT",
    "REAL", "LREAL",
    "STRING", "SSTRING",
    "BYTE", "WORD", "DWORD", "LWORD",
    "TIME", "LTIME",
    "DATE", "TIME_OF_DAY", "DATE_AND_TIME",
}

# Bit-addressable widths live in plck.models (BIT_ADDRESSABLE_WIDTHS) so
# discovery and saved-scan loading expand bits identically. Scalar integer /
# bit-string words get BOOL bit children via TagNode.expand_bits(); arrays
# are not expanded. Bit values are derived in the UI, never read per-bit.

# AB POINT I/O module suffixes that imply write-locked configuration.
# Format is `AB:1734_XXXX:C:0` for configuration data, `:I:0` for
# inputs, `:O:0` for outputs.
_WRITE_TAG_PATTERNS = (":C:", "_C:", ".Cfg")


def discover_tags(
    client: PLCClient,
    include_programs: bool = True,
    udt_max_depth: int = 8,
) -> TagTree:
    """Discover the full tag tree for a connected PLC.

    Args:
        client: A connected PLCClient. The method will call
            GetTagList(allTags=True) and (optionally) walk every
            program's tag list.
        include_programs: If True, include Program:xxx tags in the
            tree. v2.0 default — operators want to see program tags.
        udt_max_depth: Safety cap on UDT recursion. Prevents infinite
            loops if a UDT accidentally references itself.

    Returns a TagTree.

    Raises:
        PlcError: if the discovery itself fails at the protocol level
            (timeout, socket error, etc.). Per-tag failures during
            walking are logged into the node as `error` notes.
    """
    if not isinstance(client, PLCClient):
        raise TypeError("discover_tags requires a PLCClient")

    t0 = time.monotonic()
    raw_tags = client.get_tag_list(all_tags=True)
    elapsed = time.monotonic() - t0

    # pylogix's UDT cache is on the underlying client. Access via
    # _client because that's the pylogix instance, and we don't have a
    # public accessor in our PLCClient (yet). Encapsulating the access
    # here keeps the wrapper honest.
    udt_by_name: dict = client._client.UDTByName  # noqa: SLF001 (intentional; this is the only call site)

    root: list[TagNode] = []
    seen_top_level_names: set[str] = set()

    for pylogix_tag in raw_tags:
        name = pylogix_tag.TagName
        if name in seen_top_level_names:
            continue
        seen_top_level_names.add(name)

        # Skip program parent tags — we'll fetch them via GetProgramTagList
        # so we don't double-count.
        if name.startswith("Program:") and include_programs:
            continue

        node = _build_node(name, pylogix_tag.DataType, udt_by_name,
                            udt_max_depth, depth=0)
        root.append(node)

    if include_programs:
        try:
            programs = client.get_programs_list()
        except PlcError:
            programs = []
        for program in programs:
            try:
                prog_tags = client.get_program_tag_list(program)
            except PlcError:
                continue
            if not prog_tags:
                continue
            prog_node = TagNode(
                name=f"Program:{program}",
                data_type=TagDataType.OTHER,  # synthetic parent
            )
            for pt in prog_tags:
                # pylogix returns names like "Program:MainProgram.Tag";
                # strip the prefix so the child shows the bare name.
                bare = pt.TagName
                if bare.startswith("Program:"):
                    parts = bare.split(":", 2)
                    bare = parts[2] if len(parts) == 3 else bare
                child = _build_node(
                    f"Program:{program}.{bare}",
                    pt.DataType, udt_by_name, udt_max_depth, depth=0,
                )
                prog_node.members.append(child)
            root.append(prog_node)

    return TagTree(
        plc=client.plc,
        root=root,
        discovered_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
        discovery_duration_s=elapsed,
    )


def _build_node(
    name: str,
    pylogix_type: str,
    udt_by_name: dict,
    max_depth: int,
    depth: int,
) -> TagNode:
    """Build a single TagNode, recursing into UDTs if needed.

    pylogix_type comes from Tag.DataType. It can be:
        - An atomic type name (BOOL, SINT, REAL, etc.)
        - A UDT name (matches a key in UDTByName)
        - An AB module type (AB:1734_8SLOT:I:0) which is itself a UDT
        - An array type ("SINT[10]" — pylogix's Tag.Array dimension
          tells us the dimensions, pylogix_tag.DataType is the element
          type)
        - An unknown string — fall back to OTHER
    """
    is_array, array_dim, element_type = _parse_array_type(pylogix_type)

    # Atomic (non-UDT, non-array-of-UDT) leaf.
    if not is_array and element_type in _ATOMIC_TYPES:
        node = TagNode(
            name=name,
            data_type=TagDataType(element_type),
            is_write_tag=_looks_like_write_tag(name),
        )
        # Expand bit-addressable integer/bit-string words into BOOL bits.
        node.expand_bits()
        return node
    if not is_array and element_type not in udt_by_name:
        # Not atomic, not a UDT we know — call it OTHER.
        return TagNode(
            name=name,
            data_type=TagDataType.OTHER,
            is_write_tag=_looks_like_write_tag(name),
        )

    # UDT (atomic case: UDT is a struct, not an array of UDTs).
    if not is_array and element_type in udt_by_name:
        return _build_udt_node(name, element_type, udt_by_name, max_depth, depth)

    # Array of an atomic type — atomic leaf with array metadata.
    if is_array and element_type in _ATOMIC_TYPES:
        return TagNode(
            name=name,
            data_type=TagDataType(element_type),
            is_array=True,
            array_dim=array_dim,
            is_write_tag=_looks_like_write_tag(name),
        )

    # Array of UDT — recursively build the UDT and mark as array.
    if is_array and element_type in udt_by_name:
        inner = _build_udt_node(
            name, element_type, udt_by_name, max_depth, depth
        )
        inner.is_array = True
        inner.array_dim = array_dim
        return inner

    # Fallback — treat as OTHER.
    return TagNode(
        name=name,
        data_type=TagDataType.OTHER,
        is_array=is_array,
        array_dim=array_dim,
        is_write_tag=_looks_like_write_tag(name),
    )


def _build_udt_node(
    name: str,
    udt_type: str,
    udt_by_name: dict,
    max_depth: int,
    depth: int,
) -> TagNode:
    """Build a UDT parent node with member children.

    Cycle protection: if a UDT references itself (directly or via a
    chain), the depth cap stops the recursion. The cycle is rare in
    well-formed programs but possible in misconfigured ones.
    """
    if depth >= max_depth:
        return TagNode(
            name=name,
            data_type=TagDataType.UDT,
            udt_name=udt_type,
        )
    udt = udt_by_name.get(udt_type)
    if udt is None:
        return TagNode(
            name=name,
            data_type=TagDataType.UDT,
            udt_name=udt_type,
        )
    node = TagNode(
        name=name,
        data_type=TagDataType.UDT,
        udt_name=udt_type,
        is_write_tag=_looks_like_write_tag(name),
    )
    for field in udt.Fields:
        child_full = f"{name}.{field.TagName}"
        child = _build_node(
            child_full, field.DataType, udt_by_name, max_depth, depth + 1,
        )
        # If the child is itself a struct, also populate the DataType/udt_name
        if child.data_type == TagDataType.OTHER and field.Struct:
            # pylogix's Field.Struct==1 means it has its own UDT definition
            # but its DataType is a UDT name string. _build_node already
            # handled that; nothing to add here.
            pass
        node.members.append(child)
    return node


def _parse_array_type(type_str: str) -> tuple[bool, list[int], str]:
    """Parse a pylogix type string for array notation.

    pylogix returns types as 'SINT', 'REAL', 'AB:1734_8SLOT:I:0', etc.
    pylogix's separate `Tag.Array` field carries the dimensions. We
    sniff for the common 'TYPE[N]' or 'TYPE[N,M]' syntax that pylogix
    sometimes uses inline; otherwise the caller is expected to set
    `is_array` and `array_dim` from pylogix_tag.Array.

    Returns (is_array, dimensions, element_type).
    """
    s = (type_str or "").strip()
    if "[" in s and s.endswith("]"):
        head, _, rest = s.partition("[")
        dims_str, _, _ = rest.rpartition("]")
        try:
            dims = [int(d.strip()) for d in dims_str.split(",") if d.strip()]
            return True, dims, head.strip()
        except ValueError:
            return False, [], s
    return False, [], s


def _looks_like_write_tag(name: str) -> bool:
    """Heuristic: AB module configuration tags and command suffixes.

    The PLC compiler exposes External Access attributes (Read/Write/
    Read+Write) but pylogix does not surface them. Until pylogix
    supports that (issue #125), we use naming convention:

        RIO:x:C    -- POINT I/O config, writeable only in Program mode
        anything ending in Cmd / Set / Reset
        anything in the Cfg namespace

    Operators can override by right-clicking and pinning a tag as
    read-only in v2.1; for v2.0, the conservative default is to
    disable Add to Monitor for any tag matching these patterns.
    """
    if any(pat in name for pat in _WRITE_TAG_PATTERNS):
        return True
    last = name.rsplit(".", 1)[-1]
    if last.endswith("Cmd") or last.endswith("Set") or last.endswith("Reset"):
        return True
    return False
