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


def unsupported_device_message(product_name: str | None) -> str:
    """Operator-facing explanation when a device is not tag-readable."""
    label = (product_name or "").strip() or "This device"
    return (
        f"{label} is not a Logix-family PLC that PLC Toolkit can browse.\n\n"
        "Toolkit supports ControlLogix, CompactLogix, and Micro800 "
        "controllers (catalog prefixes 1756-L, 1769-L, 5069-L, 2080-L, "
        "2085-L).\n\n"
        "PanelViews, Stratix switches, and communication modules are "
        "filtered out of subnet discovery."
    )
