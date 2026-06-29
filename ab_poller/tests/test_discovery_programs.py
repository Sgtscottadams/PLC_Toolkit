from __future__ import annotations

from plck.discovery import discover_tags
from plck.comms import PLCClient
from plck.errors import PlcCommError
from plck.models import PlcConnection


class FakeTag:
    def __init__(self, name: str, data_type: str) -> None:
        self.TagName = name
        self.DataType = data_type


class FakePylogixClient:
    UDTByName = {}


class FakePLCClient(PLCClient):
    def __init__(self) -> None:
        self.plc = PlcConnection(nickname="Test PLC", ip="192.0.2.10")
        self._client = FakePylogixClient()

    def get_tag_list(self, all_tags: bool = True):
        return [FakeTag("ControllerTag", "DINT")]

    def get_programs_list(self):
        raise PlcCommError("")


def test_program_tag_discovery_is_best_effort_when_program_list_fails():
    tree = discover_tags(FakePLCClient(), include_programs=True)

    assert tree.count() == 1
    assert tree.root[0].name == "ControllerTag"
