"""Command-line entry point for `python -m plc_toolkit`."""

from __future__ import annotations

import sys

from plc_toolkit.app import main


if __name__ == "__main__":
    sys.exit(main())
