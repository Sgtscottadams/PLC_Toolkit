"""Classify EtherNet/IP devices for tag discovery support.

Subnet scans and unfiltered broadcasts return every device that answers on
44818 — PanelViews, Stratix switches, communication modules, etc. PLC Toolkit
only supports Logix-family controllers whose tags can be read via pylogix.

Use ``is_tag_readable_controller()`` at discovery time and before Connect /
Save when ``product_name`` is already known.
"""

from __future__ import annotations

# Rockwell Automation vendor ID in CIP ListIdentity / GetDeviceProperties.
ROCKWELL_VENDOR_ID = 1

# Catalog-number prefixes for controllers that expose a Logix-style tag list.
# ProductName from the PLC is typically e.g. "1756-L83E/B" — compare the
# base catalog segment before the optional "/revision" suffix.
TAG_READABLE_PRODUCT_PREFIXES: tuple[str, ...] = (
    "1756-L",   # ControlLogix / GuardLogix CPUs
    "1769-L",   # CompactLogix
    "5069-L",   # CompactLogix 5380 / 5069
    "2080-L",   # Micro800
    "2085-L",   # Micro850 / Micro870
)

# Plain-English family names keyed by the same catalog prefixes as above.
CATALOG_FAMILY_NAMES: tuple[tuple[str, str], ...] = (
    ("1756-L", "ControlLogix"),
    ("1769-L", "CompactLogix"),
    ("5069-L", "CompactLogix"),
    ("2080-L", "Micro800"),
    ("2085-L", "Micro850"),
)

# Common Allen-Bradley families that answer on EtherNet/IP but are NOT
# Logix tag-readable controllers. Used only to produce a friendly,
# specific "not supported" message (e.g. naming a MicroLogix). Order
# matters: more specific prefixes first.
NON_LOGIX_FAMILY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("1766", "MicroLogix 1400"),
    ("1764", "MicroLogix 1500"),
    ("1763", "MicroLogix 1100"),
    ("1762", "MicroLogix 1200"),
    ("1761", "MicroLogix 1000"),
    ("1747", "SLC 500"),
    ("1746", "SLC 500"),
    ("1785", "PLC-5"),
    ("1789", "SoftLogix"),
    ("2711", "PanelView"),
    ("1783", "Stratix switch"),
    ("1734", "POINT I/O adapter"),
    ("1794", "FLEX I/O adapter"),
    ("20", "PowerFlex drive"),
    ("25", "PowerFlex drive"),
)

_ROCKWELL_VENDOR_ALIASES = (
    "rockwell",
    "allen-bradley",
    "allen bradley",
)


def normalize_vendor_id(vendor: object | None) -> int | None:
    """Return numeric CIP vendor ID, or None if unknown.

    pylogix may return ``Vendor`` as ``1`` or as a string such as
    ``Rockwell Automation/Allen-Bradley`` depending on device / version.
    """
    if vendor is None:
        return None
    if isinstance(vendor, bool):
        return None
    if isinstance(vendor, int):
        return vendor
    if isinstance(vendor, float):
        return int(vendor)
    text = str(vendor).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        lower = text.lower()
        if any(alias in lower for alias in _ROCKWELL_VENDOR_ALIASES):
            return ROCKWELL_VENDOR_ID
    return None


def normalize_product_name(product_name: str | None) -> str:
    """Uppercase catalog base, strip revision suffix after '/'."""
    if not product_name or not str(product_name).strip():
        return ""
    base = str(product_name).strip().upper()
    if "/" in base:
        base = base.split("/", 1)[0]
    return base


def device_family_name(product_name: str | None) -> str:
    """Return a plain-English family label (e.g. CompactLogix) from catalog."""
    catalog = normalize_product_name(product_name)
    if not catalog:
        return ""
    for prefix, label in CATALOG_FAMILY_NAMES:
        if catalog.startswith(prefix):
            return label
    return ""


def format_device_display(
    product_name: str | None,
    *,
    ip: str = "",
) -> str:
    """Human-friendly device line: ``CompactLogix · 1769-L33ER``."""
    catalog = normalize_product_name(product_name)
    if not catalog:
        ip = (ip or "").strip()
        return ip
    family = device_family_name(product_name)
    if family:
        return f"{family} · {catalog}"
    return catalog


def is_tag_readable_controller(
    product_name: str | None,
    vendor: int | None = None,
) -> bool:
    """Return True if this device is a Logix-family CPU we can browse tags on."""
    if vendor is not None:
        vendor_id = normalize_vendor_id(vendor)
        if vendor_id is not None and vendor_id != ROCKWELL_VENDOR_ID:
            return False
    catalog = normalize_product_name(product_name)
    if not catalog:
        return False
    return any(
        catalog.startswith(prefix) for prefix in TAG_READABLE_PRODUCT_PREFIXES
    )


def filter_tag_readable_devices(devices: list[dict]) -> list[dict]:
    """Keep only devices that pass :func:`is_tag_readable_controller`."""
    out: list[dict] = []
    for d in devices:
        if is_tag_readable_controller(
            d.get("product_name"),
            d.get("vendor"),
        ):
            out.append(d)
    return out


def describe_device_type(product_name: str | None) -> str:
    """Best-effort friendly device-type label for messages.

    Prefers the supported Logix family label; otherwise tries known
    non-Logix Allen-Bradley families (MicroLogix, SLC, PLC-5, etc.);
    otherwise falls back to the raw catalog / product string.
    """
    catalog = normalize_product_name(product_name)
    family = device_family_name(product_name)
    if family:
        return f"{family} ({catalog})" if catalog else family
    for prefix, label in NON_LOGIX_FAMILY_PREFIXES:
        if catalog.startswith(prefix):
            return f"{label} ({catalog})" if catalog else label
    if catalog:
        return catalog
    raw = (product_name or "").strip()
    return raw or "This device"


def unsupported_device_message(product_name: str | None) -> str:
    """Operator-facing explanation when a device is not tag-readable."""
    desc = describe_device_type(product_name)
    return (
        f"{desc} is not supported by PLC Toolkit.\n\n"
        "PLC Toolkit can browse and monitor Logix-family controllers "
        "only: ControlLogix, CompactLogix, and Micro800 (catalog "
        "prefixes 1756-L, 1769-L, 5069-L, 2080-L, 2085-L).\n\n"
        "MicroLogix, SLC 500, PLC-5, PanelViews, Stratix switches, and "
        "communication modules use protocols this tool does not read."
    )
