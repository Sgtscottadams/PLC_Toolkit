from __future__ import annotations

import pytest

from plck.comms import PLCClient
from plck.errors import PlcCommError


def test_blank_pylogix_status_raises_actionable_message():
    client = object.__new__(PLCClient)

    with pytest.raises(PlcCommError, match="PLC returned an empty status"):
        client._raise_for_status("")
